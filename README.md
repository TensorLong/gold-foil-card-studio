# ✨ 谁还不会做金箔卡啊！保姆级教程来了

宝子们，那种**转一下卡、金线跟着扫过去**的烫金闪卡，刷到过吧？真的绝了 🥹

这个仓库把整套做法固化成 **一个 Claude Code skill + 一个 Blender 构建脚本**：你给两张图加一个 json，它还你一个**能继续改的 `.blend` 工程**和三个角度的渲染图。

敲重点：交付的不是「金卡照片」，是**活的材质**——节点组、旋钮全在，随时能拧 👌

## 🌟 它到底在干嘛

```text
Reflection → Mapping → 噪波扰动 → Add(phase) → Multiply(repeat) → Ping-Pong → 黑白渐变 = 扫光遮罩 S
线稿（白底黑线，Non-Color）→ 反相渐变 = 线条遮罩 L
最终 = S × L 的地方才发金光，其它保持印刷图
```

- 光带随**观察角度**动；卡和相机都不动时纹理不会自己滚，这点很重要
- 白底不发光，只有线条发（`L=0` vs `L=1`）
- 合成里加了一层 Fog Glow，辉光能溢出卡外
- ⚠️ 它**不做**：实体烫金工艺、彩虹全息、视差四层卡、按时间自动播放的动画

## 🎯 什么人适合用

- 想做收藏卡 / 谷子卡 / 生日贺卡，又不想手搓节点的
- 已经有插画成品，想加一层「转起来会闪」的
- 要交付**可编辑工程**给客户，而不是一张导出图
- 想把同一套材质搬到网页上做展示（有现成方案，见下）

## 📦 开工前准备

- **Blender 4.5 LTS**（脚本按 4.5+ 写，节点接口名对得上）。构建脚本只用 Blender 自带 Python，**不装任何插件**
- **Pillow**（可选，只有跑冒烟测试才要，装在系统 Python 里而不是 Blender 里）：`python3 -m pip install Pillow`
- 当 skill 用：`SKILL.md` 带 `name` / `description` frontmatter，整个仓库丢进你的 skills 目录就能被 agent 认到；默认提示词抄 `agents/openai.yaml`

## 🚀 从零跑出第一张卡

### ① 建项目目录

```text
MyCard/
├── card-config.json
└── assets/
    ├── artwork.png     # 卡面
    └── lineart.png     # 线稿，白底黑线
```

（这两个文件名是默认值，可以在配置里改成别的相对路径）

### ② 两张图的硬性规矩 —— 这段一定要看 👀

脚本会逐条校验，不合格直接报错不给跑：

- 两张图**尺寸必须完全一致**，且像素级对齐（线稿是从卡面提出来的，不是重画一张）
- **必须是不透明的完整卡面**，抠图带透明通道的会被拒
- 真 PNG，单边 ≤ 8192、总像素 ≤ 16 MP、文件 ≤ 32 MiB
- 路径必须是**项目内的相对路径**，`../` 跳出去会被拒
- 竖版：宽高比要落在 **0.3 ~ 1.0**
- 线稿要**真有黑线也真有白底**，灰蒙蒙一片会被打回

### ③ 写 `card-config.json`

不写的项自动取默认值，完整模板见 `references/config.example.json`：

```json
{
  "title": "你的烫金典藏卡",
  "assets": {"artwork": "assets/artwork.png", "lineart": "assets/lineart.png"},
  "gold": {"color": [1.0, 0.72, 0.22], "emission": 8.0, "repeat": 6.0, "phase": 0.0},
  "render": {"width": 720, "samples": 32}
}
```

### ④ 跑起来！

```bash
/path/to/blender --background --factory-startup --python-exit-code 1 \
  --python /path/to/gold-foil-card-studio/scripts/build_card.py -- \
  --project /path/to/MyCard --output /path/to/MyCard/output-v1
```

命令行参数一共就三个：

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--project` | ✅ | 放 `card-config.json` 和 `assets/` 的目录 |
| `--output` | ✅ | 输出目录，**必须是新的或空的** |
| `--skip-render` | ❌ | 只建工程不渲染，调试用 |

### ⑤ 收货 📬

```text
output-v1/gold-card.blend                  # 可编辑工程，两张贴图已打包进去
output-v1/build-report.json                # 参数、画布尺寸、Blender 版本
output-v1/renders/front|left|right.png     # 正面 / 左倾 18° / 右倾 18°
```

打开 `.blend` 直接找这两个开始调：材质 `Gold Foil Card / Printed Art + Gold Lines`、节点组 `Gold Foil / Reflection Sweep`（双击进去就是那堆旋钮）。时间轴 1–72 帧已经 K 好转卡关键帧（1 / 25 / 49 / 72），拖着看就完事 ✨

## 🎛️ 旋钮速查表

| 参数 | 默认值 | 允许范围 | 干什么的 |
| --- | --- | --- | --- |
| `color` | `[1, 0.72, 0.22]` | 每项 0 ~ 1 | 金色，**线性 RGB**，不是十六进制 |
| `emission` | `8` | 0 ~ 40 | 金线发光强度，过曝先降它 |
| `mappingRotation` | `[0, 0, 32]` | 每项 -360 ~ 360 | 光带方向，单位是度 |
| `phase` | `0` | -100 ~ 100 | 平移光带，调正面亮暗位置优先用它 |
| `repeat` | `6` | 0.01 ~ 40 | 光带重复条数（不是速度！） |
| `noiseScale` | `600` | 1 ~ 4000 | 颗粒细度 |
| `noiseAmount` | `-0.2` | -2 ~ 2 | 颗粒对光带边缘的扰动量 |
| `sweepBlack` / `sweepWhite` | `0.5` / `0.82` | 0 ~ 1 | 光带软硬，白点越靠近 1 亮部越窄 |
| `lineBlack` / `lineWhite` | `0.08` / `0.35` | 0 ~ 1 | 线稿阈值，开太宽会吞细节 |
| `render.width` | `720` | 128 ~ 4096 | 渲染宽度（整数），高度按画布比例算 |
| `render.samples` | `32` | 1 ~ 1024 | Cycles 采样数（整数） |

💡 `sweepBlack` 必须小于 `sweepWhite`，`lineBlack` 必须小于 `lineWhite`，写反了直接报错。

## 💛 想要「全金卡」？加个 `printPalette`

不是给彩色卡套层黄滤镜那种敷衍款。正确姿势是：**同一张黑白母版同时当 artwork 和 lineart**，再加这段：

```json
"printPalette": {"ink": [0.16, 0.075, 0.013], "stock": [0.68, 0.48, 0.18]}
```

`ink` 是墨线色、`stock` 是纸底色，**都是线性 RGB**。这样印刷线和发光线天生同源对齐，不用再操心配准 🎉

## 🧪 想确认装对了没

```bash
python3 /path/to/gold-foil-card-studio/scripts/smoke_test.py --blender /path/to/blender
```

它自己造一套几何测试素材跑完整流程，输出 `smoke-result.json`，还拼一张 `contact-sheet.png` 三角度对照图。看到 `"status": "PASS"` 就稳了。

⚠️ 但敲黑板：**PASS 只代表管线通了，不代表卡好看**。金色覆盖、配准、辉光范围还得你自己拿眼睛看。

## ⚠️ 踩坑预警（都是真会遇到的）

1. **千万别漏 `--python-exit-code 1`** —— 漏了的话脚本报错、Blender 也可能返回成功退出码，你以为跑通了其实啥也没有 😇
2. **别用系统 Python 直接跑 `build_card.py`** —— 它 `import bpy`，必须由 Blender 带着跑，否则只会给你一个 ImportError
3. **输出目录不能重复用** —— 脚本拒绝覆盖非空目录，报错原话是 `nothing was overwritten`。每次换个新的 `output-v2` / `output-v3`，顺便还能做版本对照 👍
4. **抠图 PNG 会被拒** —— 报错 `complete opaque artwork is required, not a cutout`，先把主体合成到完整卡面上再来
5. **线稿别拿边缘检测糊弄** —— 灰底会让整片背景一起发光，看着就是脏
6. **别改成正交相机** —— 平卡配正交时每个点反射方向一样，会变成整卡同步闪烁，一点都不高级
7. **过曝了先降 `emission` 或收窄光带** —— 别指望靠加辉光盖住配准错误，盖不住的 🥲

## 🌐 顺便还能搬到网页

`assets/renderer.js` 是配套的原生 WebGL 实现（MIT，缓冲基础改编自 LerSent001/holo-card）：

```js
import { createCardRenderer } from './assets/renderer.js';

const card = await createCardRenderer(canvas, config);
card.draw(rotateXDegrees, rotateYDegrees, emission, repeat, perspectivePixels);
card.dispose();
```

完整移植说明（预乘 alpha、10% 透明留边、GLSL 公式、浏览器验收清单）在 `references/web-port.md`，要做网页版的一定去看一眼，坑都写好了。

## 📁 仓库长这样

`SKILL.md` 制作流程与验收边界 · `scripts/build_card.py` 构建脚本（主角） · `scripts/smoke_test.py` 冒烟测试 · `references/method.md` 来源与节点方法 · `references/config.example.json` 配置模板 · `references/web-port.md` 网页移植契约 · `assets/renderer.js` WebGL 渲染器 · `agents/openai.yaml` agent 清单

## 💭 我的使用心得

- 前期 80% 的功夫都在**线稿对齐**上，这步偷懒后面全白搭
- `phase` 比 `repeat` 好用，先拿它把正面亮部推到你想要的位置
- 多开几个 `output-v*` 做参数对照，比在一个目录里反复覆盖清楚多了
- 改完一定**转着看**，静帧好看不等于转卡好看 ✨

## 📄 协议

MIT，详见 [`assets/LICENSE`](assets/LICENSE)。仓库只含文本源码，不含教程视频、原作者插画或任何来源不明的素材；二次分发前请自行确认你用的图有没有授权 🙏
