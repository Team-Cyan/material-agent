# OMLX Model Profiles

这份文档是写给“不想翻 `config.yaml`，但想知道每个本地模型为什么要有自己那套参数和 prompt 补充”的人看的。

## 一句话理解

`omlx.model_profiles` 的作用是：

- 给每个候选模型保存一套局部最佳参数
- 给每个候选模型保存一套额外 prompt 护栏
- 让你在切模型时，不用手动把 token cap、prompt 细节、建议风格再改一遍

## 它什么时候会生效

只要这两个条件成立，就会自动生效：

1. `omlx.requests.model_profile_mode: auto`
2. 当前 `full_vision_model` / `commentary_model` / `fast_vision_model` 切到了对应模型

如果你改成：

```yaml
omlx:
  requests:
    model_profile_mode: "off"
```

那就会忽略所有 `model_profiles`，只吃全局默认值。

## 一个 profile 里通常放什么

### `request_overrides`

这是“请求参数层”的局部最佳值。

典型会放：

- `prompt_preset`
- `vision_temperature`
- `commentary_temperature`
- `fast_vision_max_tokens`
- `vision_max_tokens`
- `group_commentary_max_tokens`
- `post_commentary_max_tokens`

简单理解：

- 这部分控制“这个模型多啰嗦、给它多少 token、结构稳不稳”

### `prompt_overrides`

这是“提示词补充层”的局部护栏。

典型会放：

- `full_prompt_extra`
- `group_prompt_extra`
- `post_prompt_extra`

简单理解：

- 这部分控制“这个模型别在哪些地方乱发挥”
- 比如：
  - 不要 hallucinate 人数 / 场景关系
  - 不要默认把所有问题都归因到曝光
  - 后期建议只给 2-3 条具体动作

## 当前项目里这套机制怎么用

项目默认就是：

```yaml
omlx:
  requests:
    model_profile_mode: "auto"
```

因此你平时切换：

- `Qwen3-VL-4B-Instruct-4bit`
- `Qwen3-VL-8B-Instruct-4bit`
- `gemma-4-e2b-it-4bit`
- `gemma-4-e4b-it-4bit`

时，会自动套用各自的局部最佳值。

另外有一个很重要的边界：

- `omlx-benchmark` 会自动关闭 `model_profile_mode`
- 这样 benchmark 比的是“请求组合本身”
- 不会被你本地 profile 影响

而：

- `omlx-harness` 默认保留 `model_profile_mode=auto`
- 这样 harness 比的是“真实用户路径下的综合效果”

## 当前这些 profile 各自想解决什么

### `Qwen3-VL-4B-Instruct-4bit`

它是当前默认主路径。

这套 profile 主要在压这些问题：

- `scene_raw` 乱补故事
- group commentary 容易默认回到“曝光问题”
- post commentary 容易泛化成模板化建议

所以你会看到它的 prompt 补充强调：

- `scene_raw` 要贴着可见主体和环境
- group issues 要真的跟弱项维度走
- post advice 只给 2 到 3 条具体后期动作

### `Qwen3-VL-8B-Instruct-4bit`

它的风险不是结构最差，而是“比 4B 慢很多，但收益不稳定”。

这套 profile 主要在压：

- 描述变得太散
- 点评过长
- 明明能短说，却开始补不必要背景

所以它更强调：

- `scene_raw` 保持短、字面
- post advice 只留最有价值的动作

### `gemma-4-e2b-it-4bit`

它速度很有优势，但看图更容易漂。

这套 profile 主要在压：

- 不确定时强行编细节
- 把评论说成超出给定 score context 的内容

所以它更强调：

- 不确定就保持 generic and literal
- 不要发明人数、关系、地名
- post advice 只围绕曝光、色彩、局部反差这些稳定轴

### `gemma-4-e4b-it-4bit`

它的问题比 `e2b` 更偏 hallucination 风险。

这套 profile 主要在压：

- 戏剧化 narrative
- 关系标签
- 不必要的“场景故事”

所以它的 prompt 补充更直接：

- 不要猜纪念场景 / 情侣关系 / 戏剧性叙事
- 后期建议尽量短，尽量落到 tonal / color / local adjustment

## 最推荐的调参顺序

如果你要继续调优，不要上来就改一大堆东西。

推荐顺序是：

1. 先用 `omlx-benchmark` 调请求层
2. 再用 `omlx-harness` 调 profile
3. 一次只改一个模型的一小段 `request_overrides` 或 `prompt_overrides`
4. 用同一批样片重复跑 harness

## 什么时候该改 request_overrides，什么时候该改 prompt_overrides

### 先改 `request_overrides`

如果问题更像：

- 太慢
- token 明显浪费
- 输出长度失控
- schema 稳定性不够

### 先改 `prompt_overrides`

如果问题更像：

- 描述 hallucination
- group issues 老是跑偏
- post advice 模板化
- 明明没掉曝光，却总让你先拉曝光

## 一条最实用的原则

不要追求“全模型共用一套神奇 prompt”。

在本地 OMLX 这种环境里，更现实的做法是：

- 保留全局默认值
- 给每个模型留一套很薄的局部最佳覆盖
- benchmark 看请求层
- harness 看真实输出

这样你以后切模型，才能又快又稳。
