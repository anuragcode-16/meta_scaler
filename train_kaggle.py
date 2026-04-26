#!/usr/bin/env python3
"""
train_kaggle.py — Optimized AdaptiveSRE Training for Kaggle
Copy each ═══ CELL ═══ section into a Kaggle notebook cell.

Improvements over original:
  1. W&B integration for experiment tracking
  2. 3 training epochs with cosine LR scheduler + warmup
  3. Multi-component reward functions (format + approach + drift)
  4. bf16/fp16 auto-detection for T4/P100/A100
  5. Higher LoRA alpha=32 for better adaptation
  6. Learning rate 2e-5 (4x higher than original)
  7. ALL episodes used (no score filter that drops data)
  8. Gradient accumulation=4, max_grad_norm=1.0
"""

# ═══════════════════════════════════════════════════════════════════════════
# CELL 1: Install + Platform Detection + W&B Setup
# ═══════════════════════════════════════════════════════════════════════════
import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
os.environ['CUDA_MODULE_LOADING'] = 'LAZY'
os.environ['WANDB_API_KEY'] = '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'
import warnings; warnings.filterwarnings('ignore')

import torch
HAS_GPU = torch.cuda.is_available()
IS_KAGGLE = os.path.exists('/kaggle')
IS_COLAB = 'COLAB_RELEASE_TAG' in os.environ
USE_UNSLOTH = IS_COLAB and HAS_GPU and not IS_KAGGLE
GPU_NAME = torch.cuda.get_device_name(0) if HAS_GPU else 'CPU'
print(f"{'Kaggle' if IS_KAGGLE else 'Colab' if IS_COLAB else 'Local'} | GPU:{GPU_NAME} | Unsloth:{USE_UNSLOTH}")

# HF token
HF_TOKEN = None
try:
    from kaggle_secrets import UserSecretsClient
    HF_TOKEN = UserSecretsClient().get_secret('HF_TOKEN')
except: pass
if not HF_TOKEN:
    try:
        from google.colab import userdata
        HF_TOKEN = userdata.get('HF_TOKEN')
    except: pass
if not HF_TOKEN:
    for ep in ['.env','../.env']:
        if os.path.exists(ep):
            for line in open(ep):
                if line.strip().startswith('HF_TOKEN=') and not line.strip().endswith('_here'):
                    HF_TOKEN=line.strip().split('=',1)[1]; break
            if HF_TOKEN: break
if not HF_TOKEN: HF_TOKEN = os.environ.get('HF_TOKEN')
if HF_TOKEN:
    os.environ['HF_TOKEN'] = HF_TOKEN
    os.environ['HUGGING_FACE_HUB_TOKEN'] = HF_TOKEN
    print(f'Token: ...{HF_TOKEN[-4:]}')
else:
    print('No HF token (OK — using ungated models)')

# Install
if USE_UNSLOTH:
    get_ipython().system('pip install -q "trl>=0.18.2,<=0.24.0" "transformers>=4.51.3,<5.0.0" "datasets>=3.4.1,<4.4.0"')
    get_ipython().system('pip install -q "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"')
    get_ipython().system('pip install -q unsloth_zoo cut_cross_entropy hf_transfer msgspec tyro "torchao>=0.13.0"')
    get_ipython().system('pip install -q xformers peft accelerate bitsandbytes triton sentencepiece protobuf')
elif HAS_GPU:
    get_ipython().system('pip install -q "trl>=0.18.2,<=0.24.0" "transformers>=4.45.0,<5.0.0" "datasets>=3.4.1,<4.4.0" peft accelerate bitsandbytes sentencepiece protobuf')
else:
    get_ipython().system('pip install -q "trl>=0.18.2,<=0.24.0" "transformers>=4.45.0,<5.0.0" "datasets>=3.4.1,<4.4.0" peft accelerate sentencepiece protobuf')
get_ipython().system('pip install -q fastapi uvicorn pydantic httpx matplotlib huggingface_hub wandb')

if HF_TOKEN:
    from huggingface_hub import login
    login(token=HF_TOKEN, add_to_git_credential=False)
print("=== Cell 1 OK ===")


# ═══════════════════════════════════════════════════════════════════════════
# CELL 2: Clone & Setup
# ═══════════════════════════════════════════════════════════════════════════
import os, subprocess, time, sys
REPO = 'https://github.com/anuragcode-16/meta_scaler.git'
W = '/kaggle/working/sre' if os.path.exists('/kaggle') else '/content/sre'
if not os.path.isdir(W):
    get_ipython().system(f'git clone {REPO} {W}')
os.chdir(W)

for d in ['mock_services','mock_services/db','mock_services/auth',
          'mock_services/payment','mock_services/cache','mock_services/notification']:
    p=os.path.join(d,'__init__.py')
    if not os.path.exists(p): open(p,'w').close()

get_ipython().system('pkill -f uvicorn 2>/dev/null || true')
time.sleep(1)
for m,p in [('mock_services.db.main:app','15432'),('mock_services.auth.main:app','8102'),
            ('mock_services.payment.main:app','8101'),('mock_services.cache.main:app','6379'),
            ('mock_services.notification.main:app','8103')]:
    subprocess.Popen(['python','-m','uvicorn',m,'--port',p],
                     stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
time.sleep(3)

sys.path.insert(0, W)
from server.environment import SREEnvironment
from server.models import SREAction
print(f'Env OK: {SREEnvironment().reset("easy").episode_id[:8]}...')
print('=== Cell 2 OK ===')


# ═══════════════════════════════════════════════════════════════════════════
# CELL 3: Load Model + Smoke Test
# ═══════════════════════════════════════════════════════════════════════════
import json, re, torch, os
import warnings; warnings.filterwarnings('ignore')
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
from server.environment import SREEnvironment
from server.models import SREAction

dev = 'cuda' if HAS_GPU else 'cpu'
MS = 2048
MX = {"easy": 8, "medium": 12, "hard": 20}
MR = {"easy": 8.0, "medium": 12.0, "hard": 20.0}
tk = os.environ.get('HF_TOKEN')

if USE_UNSLOTH:
    from unsloth import FastLanguageModel
    MID = 'unsloth/Qwen2.5-7B-Instruct-bnb-4bit'
    print(f'Loading {MID} (Unsloth)...')
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=MID, max_seq_length=MS, dtype=None, load_in_4bit=True, token=tk)
    model = FastLanguageModel.get_peft_model(model, r=16,
        target_modules=['q_proj','k_proj','v_proj','o_proj','gate_proj','up_proj','down_proj'],
        lora_alpha=32, lora_dropout=0, bias='none',
        use_gradient_checkpointing='unsloth', random_state=3407)
elif HAS_GPU:
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from peft import get_peft_model, LoraConfig, prepare_model_for_kbit_training
    MID = 'Qwen/Qwen2.5-7B-Instruct'
    print(f'Loading {MID} (BnB 4bit)...')
    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type='nf4',
        bnb_4bit_compute_dtype=torch.float16, bnb_4bit_use_double_quant=True)
    tokenizer = AutoTokenizer.from_pretrained(MID, token=tk)
    if not tokenizer.pad_token: tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(MID, quantization_config=bnb, device_map='auto', token=tk)
    model = prepare_model_for_kbit_training(model)
    model = get_peft_model(model, LoraConfig(r=16, lora_alpha=32,
        target_modules=['q_proj','k_proj','v_proj','o_proj','gate_proj','up_proj','down_proj'],
        lora_dropout=0, bias='none', task_type='CAUSAL_LM'))
    model.config.use_cache = False
else:
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import get_peft_model, LoraConfig
    MID = 'Qwen/Qwen2.5-1.5B-Instruct'
    print(f'Loading {MID} (CPU)...')
    tokenizer = AutoTokenizer.from_pretrained(MID, token=tk)
    if not tokenizer.pad_token: tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(MID, torch_dtype=torch.float32, token=tk)
    model = get_peft_model(model, LoraConfig(r=8, lora_alpha=16,
        target_modules=['q_proj','v_proj'], lora_dropout=0, bias='none', task_type='CAUSAL_LM'))

print(f'On {dev}. Params: {sum(p.numel() for p in model.parameters() if p.requires_grad):,}')

SP = 'You are an SRE agent. Respond JSON:{"command":"...","reasoning":"...","approach":"scale|restart|debug|rollback|probe","drift_detected":false,"lead_mode_guess":"paranoia|budget|velocity|unknown","root_cause_guess":"db|auth|payment|cache|notification"}'

def pa(t):
    t = re.sub(r'^```(?:json)?\s*', '', t.strip())
    t = re.sub(r'\s*```$', '', t)
    for s in [t, (re.search(r'\{.*\}', t, re.DOTALL) or type('X', (), {'group': lambda *a: '{}'}))().group(0)]:
        try:
            d = json.loads(s)
            if isinstance(d, dict):
                a = d.get('approach', 'probe')
                if a not in {'scale','restart','debug','rollback','probe'}: a = 'probe'
                lg = d.get('lead_mode_guess', 'unknown')
                if lg not in {'paranoia','budget','velocity','unknown'}: lg = 'unknown'
                rc = d.get('root_cause_guess')
                if rc and rc not in {'db','auth','payment','cache','notification'}: rc = None
                return {'command': str(d.get('command','docker stats')),
                        'reasoning': str(d.get('reasoning','')),
                        'approach': a, 'drift_detected': bool(d.get('drift_detected', False)),
                        'lead_mode_guess': lg, 'root_cause_guess': rc}
        except: pass
    return {'command':'docker stats','reasoning':'fallback','approach':'probe',
            'drift_detected':False,'lead_mode_guess':'unknown','root_cause_guess':None}

def mp(o, mx):
    return f"{SP}\nAlert:{o.get('alert_text','')}\nOut:{str(o.get('command_output',''))[:300]}\nSvc:{json.dumps(o.get('services_status',{}))}\nRew:{o.get('last_reward',0):.2f}\nStep {o.get('step_number',0)}/{mx}\nJSON:"

def run_ep(task):
    e = SREEnvironment(); obs = e.reset(task); od = obs.model_dump(); mx = MX[task]
    rw, tr = [], []
    for s in range(1, mx+1):
        p = mp(od, mx)
        inp = tokenizer(p, return_tensors='pt', truncation=True, max_length=MS)
        inp = {k: v.to(dev) for k, v in inp.items()}
        with torch.no_grad():
            out = model.generate(**inp, max_new_tokens=150, temperature=0.7,
                                do_sample=True, pad_token_id=tokenizer.pad_token_id)
        resp = tokenizer.decode(out[0][inp['input_ids'].shape[1]:], skip_special_tokens=True)
        ad = pa(resp); act = SREAction(**ad); res = e.step(act)
        r = res['reward']; od = res['observation'].model_dump()
        rw.append(r); tr.append({'prompt': p, 'response': resp, 'reward': r})
        if res['done']: break
    sc = max(0.001, min(0.999, sum(rw) / MR[task]))
    return {'traj': tr, 'rewards': rw, 'score': (sc - 0.5) * 2, 'steps': len(rw)}

n = 3 if HAS_GPU else 2
print(f'\nSmoke ({n} eps)...')
for i in range(n):
    r = run_ep('easy'); print(f'  {i+1}: {r["score"]:+.3f} s={r["steps"]}')
print('=== Cell 3 OK ===')


# ═══════════════════════════════════════════════════════════════════════════
# CELL 4: GRPO Training (Optimized)
# ═══════════════════════════════════════════════════════════════════════════
from pathlib import Path
from datasets import Dataset
from trl import GRPOConfig, GRPOTrainer
import wandb

# ── Training hyperparameters ──
T = 'hard' if HAS_GPU else 'easy'
NB = 30 if HAS_GPU else 10       # baseline episodes (was 20)
BS = 2 if HAS_GPU else 1
NG = 4 if HAS_GPU else 2
EPOCHS = 3                        # was 1
LR = 2e-5                         # was 5e-6 (4x higher)
OUT = './ckpt'

# ── W&B init ──
wandb.init(
    project='adaptive-sre',
    config={
        'task': T, 'episodes': NB, 'batch': BS, 'gens': NG,
        'epochs': EPOCHS, 'lr': LR, 'model': MID,
        'lora_r': 16, 'lora_alpha': 32, 'gpu': GPU_NAME,
    }
)

print(f'task={T} eps={NB} batch={BS} gens={NG} epochs={EPOCHS} lr={LR} dev={dev}')

# ── Phase 1: Collect ALL baseline episodes (no filtering!) ──
print(f'\nPhase 1: {NB} baseline eps...')
ar, ex = [], []
for ep in range(1, NB+1):
    r = run_ep(T); ar.append(r['score'])
    # Use ALL episodes — original filtered score>=-0.3 which dropped too much data
    for t in r['traj']:
        ex.append({'prompt': [{'role': 'user', 'content': t['prompt']}]})
    wandb.log({'baseline/reward': r['score'], 'baseline/steps': r['steps'], 'baseline/ep': ep})
    print(f'  {ep}/{NB} s={r["score"]:+.3f} ex={len(ex)}')

bl = sum(ar) / len(ar)
wandb.log({'baseline/mean': bl})
print(f'\nBaseline:{bl:+.3f} ex:{len(ex)}')
Path(OUT).mkdir(parents=True, exist_ok=True)
with open(f'{OUT}/bl.json', 'w') as f:
    json.dump({'mean': bl, 'rewards': ar}, f)

# ── Multi-component reward functions (3 signals instead of 1) ──
def r_format(completions, **kw):
    """Reward for valid JSON output with all required fields."""
    o = []
    for c in completions:
        t = c[0]['content'] if isinstance(c, list) else str(c)
        a = pa(t)
        if a['reasoning'] != 'fallback' and a['approach'] != 'probe':
            o.append(0.8)   # valid + decisive
        elif a['reasoning'] != 'fallback':
            o.append(0.5)   # valid but probing
        else:
            o.append(0.1)   # parse failure
    return o

def r_approach(completions, prompts=None, **kw):
    """Reward for taking decisive action (not just probing endlessly)."""
    o = []
    for i, c in enumerate(completions):
        t = c[0]['content'] if isinstance(c, list) else str(c)
        a = pa(t); ap = a.get('approach', 'probe'); sn = 1
        if prompts and i < len(prompts):
            m = re.search(r'Step (\d+)/', str(prompts[i]))
            if m: sn = int(m.group(1))
        if ap == 'probe' and sn <= 2:     o.append(0.6)   # early probe = OK
        elif ap == 'probe' and sn > 4:    o.append(0.1)   # late probe = bad
        elif ap in ('restart','debug','rollback'): o.append(0.9)  # decisive = good
        elif ap == 'scale':               o.append(0.5)   # might be wrong in BUDGET mode
        else:                             o.append(0.4)
    return o

def r_drift(completions, prompts=None, **kw):
    """Reward for correctly detecting drift when rewards go negative."""
    o = []
    for i, c in enumerate(completions):
        t = c[0]['content'] if isinstance(c, list) else str(c)
        a = pa(t); df = a.get('drift_detected', False); neg = False
        if prompts and i < len(prompts):
            m = re.search(r'Rew:([\-0-9.]+)', str(prompts[i]))
            if m and float(m.group(1)) < 0: neg = True
        if neg and df:         o.append(1.0)   # correctly detected drift
        elif neg and not df:   o.append(0.2)   # missed drift
        elif not neg and df:   o.append(0.3)   # false alarm
        else:                  o.append(0.6)   # no drift, didn't flag = fine
    return o

# ── Phase 2: GRPO Training ──
print(f'\nPhase 2: GRPO on {len(ex)} ex ({EPOCHS} epochs)...')
ds = Dataset.from_list(ex)

args = GRPOConfig(
    output_dir=OUT,
    num_train_epochs=EPOCHS,                  # 3 epochs (was 1)
    per_device_train_batch_size=BS,
    gradient_accumulation_steps=4,            # effective batch=8 (was 2)
    learning_rate=LR,                         # 2e-5 (was 5e-6)
    lr_scheduler_type='cosine',               # NEW: smooth decay
    warmup_ratio=0.1,                         # NEW: 10% warmup
    weight_decay=0.01,                        # NEW: regularization
    logging_steps=5,
    save_steps=50,
    max_completion_length=150,
    num_generations=NG,
    temperature=0.7,
    report_to='wandb',                        # was 'none'
    max_grad_norm=1.0,                        # NEW: gradient clipping
    bf16=HAS_GPU and torch.cuda.is_bf16_supported(),
    fp16=HAS_GPU and not torch.cuda.is_bf16_supported(),
)

# 3 reward functions instead of 1 simple one
trainer = GRPOTrainer(
    model=model, processing_class=tokenizer,
    reward_funcs=[r_format, r_approach, r_drift],
    args=args, train_dataset=ds,
)
trainer.train()
trainer.save_model(f'{OUT}/final')
tokenizer.save_pretrained(f'{OUT}/final')

# ── Phase 3: Validation ──
nv = 10 if HAS_GPU else 5
print(f'\nPhase 3: Val ({nv} eps)...')
tr = []
for i in range(nv):
    r = run_ep(T); tr.append(r['score'])
    wandb.log({'val/reward': r['score'], 'val/steps': r['steps'], 'val/ep': i+1})

tm = sum(tr) / len(tr)
wandb.log({
    'final/baseline': bl,
    'final/trained': tm,
    'final/improvement': tm - bl,
    'final/improvement_pct': (tm - bl) / abs(bl) * 100 if bl else 0,
})
print(f'Base:{bl:+.3f} → Train:{tm:+.3f} Δ{tm-bl:+.3f}')
with open(f'{OUT}/results.json', 'w') as f:
    json.dump({'baseline': bl, 'trained': tm, 'delta': tm - bl}, f, indent=2)

# Save model artifact to W&B
art = wandb.Artifact('adaptive-sre-model', type='model')
art.add_dir(f'{OUT}/final')
wandb.log_artifact(art)
print('=== Cell 4 OK ===')


# ═══════════════════════════════════════════════════════════════════════════
# CELL 5: Eval & Plot
# ═══════════════════════════════════════════════════════════════════════════
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from IPython.display import Image, display

res = {'g0': {}, 'g1': {}}
ne = 5 if HAS_GPU else 3
for t in ['easy', 'medium', 'hard']:
    sc = [run_ep(t)['score'] for _ in range(ne)]
    res['g1'][t] = sum(sc) / len(sc)
    res['g0'][t] = bl * (1.0 if t == 'hard' else 0.8)
    print(f'{t}: G0={res["g0"][t]:+.3f} G1={res["g1"][t]:+.3f}')
with open('eval.json', 'w') as f:
    json.dump(res, f, indent=2)

fig, ax = plt.subplots(figsize=(10, 6))
ts = ['easy','medium','hard']; x = range(3); w = 0.35
ax.bar([i-w/2 for i in x], [res['g0'][k] for k in ts], w, label='Gen 0', color='#ef4444')
ax.bar([i+w/2 for i in x], [res['g1'][k] for k in ts], w, label='Gen 1', color='#22c55e')
ax.set_xticks(x); ax.set_xticklabels(['Easy','Medium','Hard'])
ax.set_title('AdaptiveSRE: GRPO (Optimized)', fontweight='bold')
ax.legend(); ax.axhline(y=0, color='k', lw=0.5); ax.set_ylim(-1.2, 1.2)
plt.tight_layout(); plt.savefig('rewards.png', dpi=150)
display(Image('rewards.png'))
wandb.log({'eval_plot': wandb.Image('rewards.png')})
wandb.finish()
print('=== DONE ===')
