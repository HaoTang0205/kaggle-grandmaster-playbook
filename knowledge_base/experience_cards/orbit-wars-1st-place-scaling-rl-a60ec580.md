## 1. Orbit Wars: Scaling Reinforcement Learning to the Stars {#experience-orbit-wars-1st-place-scaling-rl-a60ec580}

> Competition: [Orbit Wars](https://www.kaggle.com/competitions/orbit-wars) | Source: [1st-place write-up](https://www.kaggle.com/competitions/orbit-wars/writeups/1st-place-solution-scaling-reinforcement-learnin) | Code: [IsaiahPressman/kaggle-orbit-wars](https://github.com/IsaiahPressman/kaggle-orbit-wars) | Commit: `a60ec580758ba7fe89d334223924228697e51f86` | License: MIT

### 结论摘要

这不是单一 PPO trick，而是一套大规模自博弈系统：约 2 亿参数实体 Transformer、约 150 亿环境步、Rust 并行模拟器、真实 replay parity、last-best checkpoint 评估与蒸馏、分布式 PPO，以及围绕 1 秒回合时限和 100 MiB 包大小设计的 NF4/int8/小模型 fallback。

最值得学习的是四个原则：

1. 先证明环境和训练闭环正确，再扩模型和步数。
2. 观察可以保持低层，但动作空间应做有语义的结构化分解。
3. 模拟器加速必须有 reference-transition parity gate。
4. 训练、对手评估、压缩和线上 fallback 必须共同优化。

### 任务与评估

- 多智能体 1v1 或 4-player FFA 策略游戏。
- 每个 bot 通过持续 ladder 对局更新 Gaussian skill estimate；胜负和和局影响评分，胜负幅度不影响更新。
- 采集时榜单显示 Isaiah @ Tufa Labs 排名 1、Skill Rating 1865.1。
- 关键部署约束：每回合 1 秒、总 overage 60 秒、CPU 推理、提交包 100 MiB。

### L001 先正确，再扩展

先用 1-5M 参数模型确认动作、环境、PPO 和超参数可运行，再扩到 200M、38 层、768 维、16 头，并用分布式 PPO 训练约 150 亿步。扩展成立的前提是模拟吞吐、奖励和 checkpoint 评估已经可信；最终约 2400 B200 GPU-hours 的成本不能直接迁移到普通预算。

代码：`configs/stateless_200m.yaml`、`configs/model/stateless_transformer_200m_d38.yaml`、`python/owl/train/distributed.py`。

### L002 原始实体观察 + 目标化动作

原始角度动作学习困难，最终改为 source-target attention 选择目标星球，再用截断 logistic mixture 选择连续舰队规模：

```python
q = self.q(source_x)
k = self.k(target_x)
v = self.v(target_x)
target_logits = torch.einsum("bpsd,bptd->bpst", q, k)
target_logits = target_logits / math.sqrt(self.head_dim)
```

代码：`python/owl/model/actor/discrete_targets.py:550`、`python/owl/model/actor/logistic_mixture.py`。

迁移原则：连续动作如果可以分成“候选对象 + 强度/数量”，先减少无意义几何搜索，再保留必要的连续决策。

### L003 共享实体 Transformer

星球、舰队、彗星与玩家、全局、actor-plan、critic-value、scratch tokens 共用一个 Transformer trunk。一次前向同时得到所有玩家动作和赢家概率，作者报告比逐玩家推理节省约 2-4 倍计算。

代码：`python/owl/model/stateless_transformer_v1.py:291`、`:325`、`:596`、`:708`。

### L004 Rust 环境必须通过真实 replay parity

Rust vector environment 使用 Rayon 并行推进环境和写观测，Python 侧复用 pinned buffers。真实 Kaggle episode 被转成逐转移 fixture，Rust 重新执行后比较全部状态：

```rust
let result = step_with_injections(&mut state, &actions, &mut rng, injections);
compare_state(&state, &result, row)?;
```

代码：`src/rl/vec_env.rs:286`、`src/rules_engine/replay_tests.rs:95`、`:273`、`python/owl/rl.py:339`。

### L005 last-best 晋升和 teacher 稳定

当前 checkpoint 定期与 last-best 进行 1v1/2v2 评估，总胜率达到 70% 才替换。last-best 还提供 action KL 与 winner-distribution value cross-entropy：

```python
replace_last_best = (
    eval_metrics["eval/win_rate_against_last_best"] >= 0.7
)
```

```python
loss = (
    policy_loss
    + vf_coef * value_loss
    - ent_coef * entropy_mean
    + teacher_kl_loss
    + teacher_value_loss
)
```

代码：`scripts/run_ppo.py:443`、`python/owl/train/ppo.py:1478`。

多人非传递博弈中只对 last-best 仍可能遗漏策略循环，应该增加历史 checkpoint league 和对手矩阵。

### L006 部署约束进入模型选择

- NF4 group-128 checkpoint 压缩。
- CPU Linear 动态 int8，输出头保持浮点。
- 过滤小舰队控制 token 数。
- overage 过低时切到约 5M fallback。
- 三比特压缩虽然能放更大模型，但策略损失不值得，因此被否决。

代码：`python/owl/agent/agent.py:235`、`:373`、`:439`、`python/owl/checkpoint_quantization.py:812`。

### 失败经验

#### gamma=1 的拖延策略

无折扣保持了多人赢家概率 critic 的定义，却让领先策略没有尽早获胜的激励，已经决定的局面继续消耗 rollout。可测试提前截断或投降，但必须确认不会改变真实胜负目标。

#### 训练模式分布过拟合

作者后半程把 2-player 比例提高到 90%，并为吞吐省略 league play；截止后榜单顶端对局却转向 4-player。在线 ladder 分布会漂移，训练 mixture 应用 2p/4p × 历史 checkpoint 矩阵验证，而不是拟合近期匹配。

#### 动作 mask 反而降低质量

阻止明显错误发射的 mask 曾让模型更弱，可能因为无 mask 迫使模型学习完整物理。该观察没有公开完整消融数字，应作为实验假设而不是规则。

#### Agentic coding 不能替代研究决策

Codex 显著缩短了工程周期，但作者明确指出其建议和创造性不能替代思考。讨论区还有参与者反馈，持续在同一 agentic codebase 上堆实验最终失控。应使用独立 workspace/worktree、淘汰失败分支并保留可回滚基线。

### 代码佐证索引

#### CE001 结构化目标动作（L002）

来源：`python/owl/model/actor/discrete_targets.py:550-586`

```python
q = self.q(source_x)
k = self.k(target_x)
v = self.v(target_x)
target_logits = torch.einsum("bpsd,bptd->bpst", q, k)
target_logits = target_logits / math.sqrt(self.head_dim)
target_logits = target_logits.masked_fill(
    ~can_act,
    torch.finfo(target_logits.dtype).min,
)
```

#### CE002 共享实体 Token（L003）

来源：`python/owl/model/stateless_transformer_v1.py:291-328`

```python
self.fleet_proj = ObservationInputStem(
    self.obs_spec.fleet_channels, self.config
)
self.comet_proj = ObservationInputStem(
    self.obs_spec.comet_channels, self.config
)
self.player_tokens = nn.Parameter(torch.empty(OUTER_PLAYER_SLOTS, dim))
self.actor_plan_tokens = nn.Parameter(torch.empty(OUTER_PLAYER_SLOTS, dim))
self.critic_value_tokens = nn.Parameter(torch.empty(OUTER_PLAYER_SLOTS, dim))
```

#### CE003 真实 Replay 一致性门（L004）

来源：`src/rules_engine/replay_tests.rs:95-134`

```rust
for fixture_path in fixture_paths {
    let file = File::open(&fixture_path)?;
    for line in BufReader::new(file).lines() {
        let row: FixtureRow = serde_json::from_str(&line?)?;
        let result = check_transition(&row)
            .map_err(|message| format!("{} step {}: {message}", row.episode_id, row.step))?;
    }
}
```

#### CE004 Last-best 晋升门（L005）

来源：`scripts/run_ppo.py:410-449`

```python
eval_metrics = _evaluate_against_last_best(
    current_model=unwrap_model(trainer.model),
    last_best_model=last_best_model,
    cfg=cfg,
    device=trainer.device,
)
replace_last_best = (
    eval_metrics["eval/win_rate_against_last_best"]
    >= LAST_BEST_WIN_RATE_THRESHOLD
)
```

#### CE005 NF4 分组量化（L006）

来源：`python/owl/checkpoint_quantization.py:812-851`

```python
group_count = (cols + _NORMALFLOAT_GROUP_SIZE - 1) // _NORMALFLOAT_GROUP_SIZE
groups = padded.reshape(rows * group_count, _NORMALFLOAT_GROUP_SIZE)
max_abs = valid_abs_groups.amax(dim=1, keepdim=True)
scale = max_abs
codes = torch.bucketize(groups / safe_scale, thresholds).to(torch.long)
quantized = values[codes]
```

### 来源边界

公开仓库在方案形成后继续演进；当前 HEAD 的 LoRA、新 reward mode 和额外量化能力不能自动归因给获胜提交。方案结论以 `docs/write-up.md` 为主，代码定位固定到提交 `a60ec580`。仓库未附带最终 200M checkpoint 或不可变提交归档，因此无法从零复现作者的榜单强度，只能复现实现框架和小规模实验。

### 检索关键词

`reinforcement learning`, `self-play`, `PPO`, `multi-agent`, `opponent pool`, `league play`, `last-best checkpoint`, `teacher KL`, `entity transformer`, `structured action`, `Rust simulator`, `replay parity`, `distributed PPO`, `NF4`, `int8`, `fallback model`, `gamma stalling`, `opponent shift`, `agentic coding`, `强化学习`, `自博弈`, `多智能体`, `环境加速`, `对手池`, `量化部署`
