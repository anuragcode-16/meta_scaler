import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import os, json

os.makedirs("plots", exist_ok=True)

# === Plot 1: Reward Comparison ===
fig, ax = plt.subplots(figsize=(10, 6))
tasks = ["Easy\n(Static Lead)", "Hard\n(Drifting Lead)"]
baseline = [-0.195, -0.158]
trained = [-0.167, -0.030]
x = range(len(tasks))
w = 0.35

ax.bar([i - w/2 for i in x], baseline, w, label="Gen 0 (Baseline)", color="#ef4444", alpha=0.8)
ax.bar([i + w/2 for i in x], trained, w, label="Gen 1 (GRPO Trained)", color="#22c55e", alpha=0.8)

for i, (b, t) in enumerate(zip(baseline, trained)):
    ax.annotate(f"{b:+.3f}", xy=(i - w/2, b), ha="center", va="bottom", fontsize=10, fontweight="bold")
    ax.annotate(f"{t:+.3f}", xy=(i + w/2, t), ha="center", va="bottom", fontsize=10, fontweight="bold")

ax.set_ylabel("Mean Episode Reward", fontsize=12)
ax.set_title("AdaptiveSRE: GRPO Reward Improvement", fontsize=14, fontweight="bold")
ax.set_xticks(x)
ax.set_xticklabels(tasks)
ax.legend(fontsize=11)
ax.axhline(y=0, color="black", linewidth=0.5)
ax.set_ylim(-0.4, 0.1)
plt.tight_layout()
plt.savefig("plots/reward_curve.png", dpi=150)
print("Saved plots/reward_curve.png")

# === Plot 2: Training Loss ===
fig, ax = plt.subplots(figsize=(10, 5))
steps = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60]
loss = [0.0, 0.034, -0.018, 0.0, 0.014, 0.0, 0.0, 0.0, 0.0, 0.0, 0.013, 0.028]
ax.plot(steps, loss, marker="o", linewidth=2, markersize=6, color="#3b82f6")
ax.fill_between(steps, loss, alpha=0.2, color="#3b82f6")
ax.set_xlabel("Training Step", fontsize=12)
ax.set_ylabel("Loss", fontsize=12)
ax.set_title("AdaptiveSRE: GRPO Training Loss (Easy Task)", fontsize=14, fontweight="bold")
ax.axhline(y=0, color="black", linewidth=0.5, linestyle="--")
plt.tight_layout()
plt.savefig("plots/loss_curve.png", dpi=150)
print("Saved plots/loss_curve.png")

# === Plot 3: Alignment Score Demo ===
fig, ax = plt.subplots(figsize=(10, 4))
steps_demo = list(range(1, 13))
alignment = [0.82, 0.84, 0.81, 0.83, 0.85, 0.84, 0.86, 0.12, 0.09, 0.15, 0.45, 0.71]
ax.plot(steps_demo, alignment, marker="o", linewidth=2.5, color="#8b5cf6")
ax.axvline(x=8.5, color="red", linestyle="--", alpha=0.7, label="Policy Drift")
ax.annotate("Drift occurs", xy=(8.5, 0.85), xytext=(6, 0.95),
            arrowprops=dict(arrowstyle="->", color="red"), fontsize=10, color="red")
ax.annotate("Agent detects\n& recovers", xy=(11, 0.71), xytext=(9.5, 0.5),
            arrowprops=dict(arrowstyle="->", color="green"), fontsize=10, color="green")
ax.set_xlabel("Episode Step", fontsize=12)
ax.set_ylabel("Alignment Score", fontsize=12)
ax.set_title("AdaptiveSRE: Policy Drift Detection & Recovery", fontsize=14, fontweight="bold")
ax.legend()
ax.set_ylim(0, 1)
plt.tight_layout()
plt.savefig("plots/alignment_demo.png", dpi=150)
print("Saved plots/alignment_demo.png")

print("\nAll plots generated.")
