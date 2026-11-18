# 本地 AI 3D 海报流水线

**Qwen-Image 2.1（UC INT8）→ Hunyuan3D 2.1 → Blender 4.2 → 4K 静帧**

这套东西解决一件事：不用任何付费 API，在自己机器上把「一句话」变成一张 3840×2160 的电影感产品图，同时留下可复现的 GLB、.blend 和 run.json。

第一件测试作品是科幻头盔 `helmet01`；第二件用复古相机 `camera01` 验证了模板不绑题材。换题材主要是换提示词和项目名；摄影棚的构图参数（相机距离、产品台半径）按新物体的长宽比微调。

```
提示词 ──> Qwen 2.1 出 4 张概念图
              │
              ├─> Qwen 2.1 图像编辑：清背景 / 去杂物 → hy_input.png
              │
              └─> Hunyuan3D 2.1 单图出形状 → model.glb（白模，无贴图）
                        │
                        └─> Blender：导入 / 清理 / 材质 / 打光 / 相机
                                  │
                                  ├─> 1K 预览（快速调）
                                  └─> CLI 渲 4K（128 samples，16-bit PNG）
```

---

## 0. 先读：三条硬约束

1. **只做非商用。** `abenzerps/Qwen-Image-2.1-Uncensored-Quantized` 的元数据仍是 **Qwen Research License**，只允许研究/非商用。Hunyuan3D 2.1 是 **Community License**，商业使用有 MAU 与地区限制，以官方 LICENSE 为准。
2. **Hunyuan3D 2.1 只吃单视图。** 不要把手绘的 FRONT/SIDE/BACK 转身表整张喂进去。转身表只给人看，用来保持设计一致。
3. **它擅长硬表面，不擅长角色。** 头盔、枪械、相机、机器人外壳、载具零件效果好；人脸、手指、布料、毛发容易崩。这个模板的定位是「产品/道具海报」，不是游戏资产或 3D 打印。

另外：这个 UC 量化版**没有内容过滤器**。生成什么由你负责；不要用于违法、侵权、冒充他人或 deceptive 内容。

---

## 1. 这套流程最后会留下什么

以 `helmet01` 为例：

| 文件 | 作用 |
|---|---|
| `~/ai3d/projects/helmet01/refs/*.png` | Qwen 出的 4 张概念图 + `hy_input.png` |
| `~/ai3d/projects/helmet01/model.glb` | Hunyuan 出的白模 |
| `~/ai3d/blend/helmet01.blend` | Blender 工程（模型、材质、灯光、相机） |
| `~/ai3d/renders/helmet01_preview.png` | 1600×900 小样 |
| `~/ai3d/renders/helmet01_4k.png` | 3840×2160、16-bit 母版 |
| `~/ai3d/renders/helmet01_poster_edit_2k.png` | 2048×1152 电影感变体（Qwen 编辑加氛围与视缝辉光） |
| `~/ai3d/renders/run_edit_*.json` | 海报变体的编辑提示词、seed、prompt_id、耗时 |
| `~/ai3d/projects/helmet01/run_*.json` | 每次 ComfyUI 运行的 prompt / seed / 模型 / prompt_id / 耗时 |
| `~/ai3d/projects/helmet01/run.json` | 汇总：各阶段、权重 sha256、渲染参数、所有 ComfyUI 运行记录 |
| `~/ai3d/logs/*.log` | ComfyUI、下载、渲染日志 |

---

## 2. 目录地图

```
~/ai3d/
├── workflows/api/        # 给脚本用的 API 工作流（qwen_t2i / qwen_edit / hy3d）
├── workflows/ui/         # 给人看的 UI 工作流（备查）
├── prompts/              # 提示词模板 + 每个项目的提示词
├── projects/<名字>/      # 每个项目的输入、GLB、run.json
│   ├── rig.json          # 可选：骨架配置（件/骨/权重/预览/验收）
│   ├── parts/            # 可选：分件工程、单件 GLB、预览、manifest
│   └── rig/              # 可选：骨架工程、绑定 GLB、姿态预览、两份报告
├── blend/                # Blender 工程
├── renders/              # 预览和 4K 成品
├── scripts/
│   ├── comfy_run.py      # ComfyUI 命令行：t2i / edit / hy3d
│   ├── gen_concepts.sh   # 一次出 4 张概念图
│   ├── whiten_bg.py      # 把边缘连通的近白背景涂成纯白
│   ├── new_project.sh    # 建项目目录
│   ├── check_env.sh      # 环境自检
│   ├── download_weights.sh
│   ├── finalize_weights.sh
│   ├── render_final.sh   # CLI 渲 4K / 预览
│   └── blender/          # 分阶段脚本（25_parts 分件、32_rig 绑定、35 验收；run_rig.py 一键）
├── logs/
└── backups/              # 升级前的 venv / 配置
```

---

## 3. 本机环境（2026-10-20 的实际状态）

| 项目 | 值 |
|---|---|
| GPU | RTX 3080 20GB（Ampere；不支持 FP8/FP4） |
| 内存 | 125GB |
| ComfyUI | v0.42.1，`~/ComfyUI`，端口 8188 |
| PyTorch | 2.11.0 + cu128 |
| Blender | 4.2.10 LTS，`~/.local/bin/blender` |
| Blender MCP | 插件 1.8，协议 13，端口 9876 |
| 权重 | Qwen UC 三件套 + Hunyuan3D 2.1，共约 24.3GB |

**升级前的备份（回滚用）：**

- 分支：`backup/pre-qwen-20261020`
- venv：`~/ai3d/backups/venv-0.33`
- requirements：`~/ai3d/backups/requirements-0.33.txt`
- 启动脚本：`~/ai3d/backups/start.sh.pre-ai3d`

---

## 4. 第一次用：按顺序走

每一步都按 **做什么 / 怎么敲 / 怎么算成功 / 失败查哪** 写。命令可以直接复制，路径已经写成绝对路径，不依赖当前目录。

### 4.1 环境自检

**做什么**：确认 ComfyUI、Blender、四份权重、GPU、磁盘都在位。

**怎么敲**：

```bash
~/ai3d/scripts/check_env.sh
```

**怎么算成功**：

- 最后一行是 `环境自检通过。`
- 看到 `ComfyUI 0.42.1 @ 8188`
- 四个权重都显示 GB 数，没有 `[×]`
- `9876 在听`（Blender 开着）

**失败查哪**：

- `8188 没响应` → 先按 4.2 启动 ComfyUI。
- `9876 没在听` → Blender 没开，或 MCP 插件没 Start Server。Blender 打开后插件会自动监听；没有再手动开。
- 权重大小不对 → 按 4.3 重下，别硬跑。

---

### 4.2 启动 ComfyUI

**做什么**：把 ComfyUI 服务拉起来。它只监听本机/局域网，不联网也可以跑。

**怎么敲**：

```bash
cd ~/ComfyUI
./start.sh
```

想放后台：

```bash
cd ~/ComfyUI
nohup ./start.sh > ~/ai3d/logs/comfyui.log 2>&1 &
```

确认版本和端口：

```bash
curl -s localhost:8188/system_stats | head -c 300
ss -ltn | grep 8188
```

**怎么算成功**：

- 返回 JSON 里有 `"comfyui_version": "0.42.1"`
- 端口 8188 在听
- `~/ai3d/logs/comfyui.log` 里没有 `IMPORT FAILED`
- 浏览器打开 `http://127.0.0.1:8188` 能看到界面

**失败查哪**：

- 服务起不来：看日志最后 30 行；常见是自定义节点和新版冲突。
- `IMPORT FAILED`：先把报错的自定义节点移到 `~/ai3d/backups/custom_nodes/`，再启动。VibeVoice 报错不影响本流程。
- 完全确认是 ComfyUI 升级问题 → 按第 8 节回滚。

> 本机启动参数已经加了 `--reserve-vram 0.6`，并保留 `--disable-smart-memory`。前者给系统留 0.6GB 显存，后者避免模型在显存/内存之间反复搬。

---

### 4.3 下载并校验权重

**做什么**：把 Qwen 三件套下到临时目录，校验后再移进 ComfyUI；Hunyuan 直接下到 `models/checkpoints/`。

**怎么敲**：

```bash
~/ai3d/scripts/download_weights.sh
```

下载完成后**必须**再跑：

```bash
~/ai3d/scripts/finalize_weights.sh
```

**怎么算成功**：

- 四个文件大小完全一致：
  - DiT：`7256796840` 字节
  - 文本编码器：`9350798360`
  - VAE：`675509688`
  - Hunyuan：`7365943290`
- `sha256sum -c expected.sha256` 三行全 `OK`
- Hunyuan 的 sha256 也是 `OK`
- 四个 `.safetensors` 的头部都能解析
- 最后打印 `全部校验通过，权重就位。`
- `~/ai3d/logs/weights_verified.txt` 有四个 sha256

**失败查哪**：

- 下载长时间 0 字节：`HF_ENDPOINT=https://hf-mirror.com`、`HF_HUB_DISABLE_XET=1`，`curl -C -` 续传；不要同时对同一个文件开两个 curl。
- 大小差一点：删掉该文件重下，不要用残缺文件跑模型。
- `sha256sum -c` 失败：文件损坏或被替换，删掉重下。
- 注意：这个仓库的 `SHA256SUMS` **没有** INT8 DiT 那一行（只有 GGUF/MLX/NVFP4、文本编码器和 VAE）。DiT 的 sha256 取自 Hugging Face 的 LFS 元数据，已写死在 `finalize_weights.sh` 里。

**为什么不用 NVFP4 / MLX / GGUF / 多视图：**

- NVFP4 需要 Blackwell（50 系），30 系跑不了。
- MLX 是苹果芯片专用。
- GGUF Q4_K_M（4.6GB）是显存吃紧时的后备，要另装 `ComfyUI-GGUF` 节点，并把 `UNETLoader` 换成 `Unet Loader (GGUF)`；本期先用 INT8 safetensors，少一个变量。
- Hunyuan 2.1 是单视图；多视图节点是 2.0 MV 的，不要混用。
- 官方 t2i 模板还带一个 8.8GB 的提示词增强器（Qwen 3.5 9B）。本期不下载：它只改写提示词，不减画质；先用自己写的提示词，出图不满意再考虑补。

---

### 4.4 出 4 张概念图

**做什么**：用 Qwen-Image 2.1 出 4 张白底、单件、完整入画的头盔概念图。

**怎么敲**：

```bash
~/ai3d/scripts/gen_concepts.sh helmet01
```

它等价于跑 4 次：

```bash
python3 ~/ai3d/scripts/comfy_run.py t2i \
  --prompt "$(cat ~/ai3d/prompts/helmet01_concept.txt)" \
  --seed 202 --batch 1 \
  --outdir ~/ai3d/projects/helmet01/refs
```

**怎么算成功**：

- `~/ai3d/projects/helmet01/refs/` 里有 4 张 PNG
- 每张 1024×1024、不是全黑
- 头盔是**单件**、3/4 视角、完整入画、白底、没有手/脖子/文字
- 每次运行目录里多一个 `run_t2i_*.json`，记录 seed 和 prompt_id

快速检查尺寸和亮度：

```bash
~/ComfyUI/venv/bin/python - <<'PY'
from PIL import Image, ImageStat
import glob
for p in sorted(glob.glob('/home/roland/ai3d/projects/helmet01/refs/*.png')):
    im = Image.open(p)
    m = ImageStat.Stat(im.convert('RGB')).mean
    print(p.split('/')[-1], im.size, 'mean', round(sum(m)/3, 1))
PY
```

`mean` 太低（< 5）就是黑图，别往下走。

**失败查哪**：

- 黑图：确认三个加载器都指向 UC 权重；VAE 文件名对；steps 25 / cfg 1.0 / euler simple 不要乱改。
- OOM：保持 `--batch 1`；关掉 Blender 的 4K 渲染；确认 `--reserve-vram 0.6`；每轮结束脚本会 `/free`。还不行，把文本编码器换成官方 `qwen3vl_8b_w4a8.safetensors`（6.31GB）。
- 图里有多件物体/手/文字：直接重跑换 seed，或走 4.5 的图像编辑清一遍。提示词里已经写了 no text / single object，但模型仍可能加戏。
- 质量明显塌陷：先跑 4 张再判断；仍不行才考虑 Q6_K GGUF 或官方 int8。

**关于转身表**：`~/ai3d/prompts/helmet01_turnaround.txt` 可以用来出 FRONT/SIDE/BACK 设定图，保持设计一致。**只给人看，不喂 Hunyuan3D。**

想生成：

```bash
python3 ~/ai3d/scripts/comfy_run.py t2i \
  --prompt "$(cat ~/ai3d/prompts/helmet01_turnaround.txt)" \
  --seed 777 --batch 1 \
  --outdir ~/ai3d/projects/helmet01/refs
```

---

### 4.5 选图并清成单物体 `hy_input.png`

**做什么**：挑轮廓最清楚的一张，用 Qwen 2.1 图像编辑去掉背景杂物、地面阴影和裁切，输出一张 1024 的白底单物体图。

**怎么敲**：

先看一眼 4 张图，把选中的那张复制成 `chosen.png`：

```bash
cp ~/ai3d/projects/helmet01/refs/<你选的那张>.png \
   ~/ai3d/projects/helmet01/refs/chosen.png
```

然后：

```bash
python3 ~/ai3d/scripts/comfy_run.py edit \
  --image ~/ai3d/projects/helmet01/refs/chosen.png \
  --prompt "$(cat ~/ai3d/prompts/helmet01_clean.txt)" \
  --seed 1201 --resolution 1024 \
  --outdir ~/ai3d/projects/helmet01/refs \
  --name hy_input.png
```

**强烈建议再走一遍纯白化**（尤其相机这种带淡阴影的图）：

```bash
~/ComfyUI/venv/bin/python ~/ai3d/scripts/whiten_bg.py \
  ~/ai3d/projects/helmet01/refs/hy_input.png \
  ~/ai3d/projects/helmet01/refs/hy_input_white.png
```

然后把 4.6 的 `--image` 换成 `hy_input_white.png`。它只涂“和图像边缘连通”的近白像素，不会吃掉物体内部的高光。

**为什么多这一步**：Hunyuan 会把很淡的阴影或 249–254 的灰底当成真实几何。`camera01` 第一次没纯白化，重建结果是一块 `0.35×0.35×0.088` 的薄板（相机被压扁、98% 面是“阴影板”）；纯白化后变成 `0.35×0.21×0.21` 的正常相机比例，减面也能正常到 25 万。

**怎么算成功**：

- `refs/hy_input.png` 存在，1024×1024 左右
- 纯白或接近纯白背景；纯白化后像素应为 255
- 头盔完整、居中、没有手/文字/地面阴影
- 轮廓干净，暗部没有和背景糊在一起
- `whiten_bg.py` 打印“背景涂白 …%”（`camera01` 样本是 73.5%）

**失败查哪**：

- 编辑结果几乎没变：确认 `qwen_edit.json` 里 `LoadImage` 的图已上传，`images.image_1` 接的是 `["4", 0]`；`KSampler` 的 latent 接的是 TextEncode 的第 3 个输出（`["5", 2]`）。
- 背景没清干净：换 seed 或把提示词写得更具体（`pure white seamless background, no floor shadow`）；仍有 249–254 的灰底就用 4.5 的 `whiten_bg.py`。
- 输出尺寸不对：`--resolution 1024` 是参考图预算；输出跟随输入图的长宽比。
- 不想用 Qwen 编辑：也可以用 GIMP/Photoshop 手动抠图，只要最后是白底、单物体、完整入画即可。

---

### 4.6 Hunyuan3D 出模

**做什么**：把 `hy_input_white.png`（纯白化后的图）变成白模 GLB。`helmet01` 这张的 `hy_input.png` 本身已经够白，实际跑的是它；新图建议统一走 `white` 版本。

**怎么敲**：

```bash
python3 ~/ai3d/scripts/comfy_run.py hy3d \
  --image ~/ai3d/projects/helmet01/refs/hy_input_white.png \
  --outdir ~/ai3d/projects/helmet01 \
  --name model.glb
```

**怎么算成功**：

- `~/ai3d/projects/helmet01/model.glb` 存在
- 大于 1MB（太小通常意味着空网格/破面）
- `run_hy3d_*.json` 里 prompt_id、耗时、模型名齐全
- 脚本最后会 `/free` 卸载 Hunyuan，给 Blender 让显存

**失败查哪**：

- GLB 很小或导入没面：换一张更干净的白底图；阈值从 0.6 调到 0.55–0.65；`octree` 保持 256。
- 模型缺一半/有洞：输入图里物体被裁切，或背景不干净。回到 4.5。
- 出模很慢：30 步、4096 分辨率、octree 256 是官方默认；单次 3–8 分钟正常。
- 不要喂转身表：2.1 只支持单视图，整张转身表会得到四不像。

---

### 4.7 Blender 导入、清理、材质、打光

**做什么**：把 GLB 导进 Blender，统一尺寸、清网格、上程序化金属/橡胶材质、搭摄影棚。

**先启动 Blender GUI**：

```bash
~/.local/bin/blender ~/ai3d/blend/helmet01.blend &
```

第一次没有这个文件就直接开空场景：

```bash
~/.local/bin/blender &
```

插件 1.8 会自动监听 9876。确认：

```bash
ss -ltn | grep 9876
```

**怎么敲**：在 Qoder 里让 Blender MCP 执行下面这段（每个阶段只改 `AI3D_STAGE`）：

```python
import os
os.environ["AI3D_PROJECT"] = "helmet01"
os.environ["AI3D_STAGE"] = "import"   # 依次换成 clean / materials / studio / render
exec(open("/home/roland/ai3d/scripts/blender/run_stage.py").read())
```

也可以在 Blender 的 Python Console 里粘贴同一段。

阶段顺序与作用：

| 阶段 | 作用 | 成功标志 |
|---|---|---|
| `import` | 导入 GLB、合并、最大边归一化到 0.35m、底面落地 | 尺寸约 `0.3×0.3×0.35`，底部 `z=0` |
| `clean` | 去松散点、按距离合并、去碎块、重算法线、35° 平滑、抽到约 25 万三角面 | 无松散点，面数合理 |
| `materials` | 金属 + 橡胶两套 Principled；Bevel Shader 倒角；Pointiness 边缘磨损；Noise 粗糙度/凹凸 | 材质列表里有 `Helmet_Metal`、`Helmet_Rubber` |
| `studio` | 无缝背景、产品台、青色发光环、5 盏面积光、80mm 相机、AgX Medium High Contrast、轻微 Glare | 场景里有相机和 5 盏灯 |
| `render` | 4K、128 samples、adaptive 0.01、OIDN 降噪、16-bit PNG | 打印 `4K 渲染参数就绪` |

每阶段结束会自动保存 `~/ai3d/blend/helmet01.blend`，并打印 `[OK] 阶段 ... 完成`。

**怎么算成功**：

- `import` 打印的尺寸最大边约 `0.35`
- `clean` 打印 `shade_smooth_by_angle 35.0°`，没有 `[×]`
- `materials` 打印两种材质的面数分配
- `studio` 打印相机位置和 5 盏灯
- `render` 打印 3840×2160 / 128 samples

**失败查哪**：

- `ModuleNotFoundError: _common`：`run_stage.py` 里脚本目录被固定为 `~/ai3d/scripts/blender`；如果你把项目挪了地方，设置 `AI3D_SCRIPT_DIR=...`。
- `join 失败`：脚本会自动退回逐网格合并；看日志确认没有丢件。
- 法线反了/表面发黑：`clean` 已重算法线；仍有问题就在 Blender 里 `Shift+N` 重算外侧。
- 抽面太狠丢细节：设置 `AI3D_TRIS=400000` 再跑 `clean`。
- 材质太亮/太暗：改 `30_materials.py` 里的 `Roughness` / `Metallic`，只重跑 `materials`。
- 整件偏橡胶/材质分配不对：脚本把“底部 8.5% 高度”判成橡胶；设 `AI3D_RUBBER=0` 重跑 `materials` 得到全金属，或改 `30_materials.py` 里的 `0.085` 比例。
- 低矮/宽扁物体在画面里太小：摄影棚按 0.35m 高的头盔调的（80mm、约 2m 距离）。改 `50_studio.py` 的 `cam.location` / `cam_data.lens`，或用 `AI3D_PLINTH_R=0.2` 缩小产品台，再跑 `studio`。
- MCP 无响应：重启 Blender；每个阶段脚本都是幂等的，可以放心重跑。
- `look` 工具在当前 MCP 服务上报错（已实测）；用 4.8 的预览渲染代替，不影响主线。

**Blender 4.2 的两个坑（脚本已经处理）：**

- 没有 auto smooth：用 `bpy.ops.object.shade_smooth_by_angle(angle=...)`。
- Principled 的插槽叫 `Transmission Weight`、`Coat Weight`，不是 3.x 的旧名字。
- 不要给 AI 高模加 Bevel 修改器，会炸面；脚本用的是 Cycles 的 Bevel Shader 节点。

---

### 4.8 预览与 4K 渲染

**做什么**：先用 1600×900 / 32 samples 快速看构图和灯，再渲 4K 母版。最终渲染**不走 MCP**，用命令行，避免 MCP 超时和 Blender GUI 崩掉影响结果。

**怎么敲**：

```bash
# 1K 预览，本机实测约 9 秒
~/ai3d/scripts/render_final.sh helmet01 preview

# 4K 母版，本机实测约 1 分钟（128 samples / OIDN）
~/ai3d/scripts/render_final.sh helmet01
```

**怎么算成功**：

- 预览：`~/ai3d/renders/helmet01_preview.png`，1600×900
- 4K：`~/ai3d/renders/helmet01_4k.png`，`file` 显示 `3840 x 2160`
- 文件大于 2MB；画面不是全黑
- 日志最后没有 `CUDA error` / `out of memory`
- 脚本会把本次渲染的分辨率、samples、耗时、文件大小写进 `projects/helmet01/run.json` 的 `stages.render`

**失败查哪**：

- 黑图：先看预览；检查相机是否在模型里、灯光是否被禁用、World 强度是否 0；曝光是否被拉到 -5。
- 4K 太慢：把 `60_render.py` 的 samples 降到 96，或先用 2560×1440。
- 掉卡/CUDA error：`nvidia-smi` 看 Xid；crashcam 一直在跑；直接重跑 `render_final.sh`，已保存的 .blend 不会丢。连续失败就把分辨率降到 2560×1440。
- 渲染成功但文件名不对：`render_final.sh` 用 `write_still=True` 直接写目标路径，不经过帧号拼接。

**构图不满意怎么办**：

- 只改灯/相机：重跑 `studio`（会重建灯和相机，不会动模型材质），再 preview。
- 只改材质：重跑 `materials`，再 preview。
- 只改模型：重跑 `import → clean → materials → studio`，因为导入会清空 `AI3D` 集合。
- 换成长条、矮扁或特别高的物体：先改 `50_studio.py` 里的相机距离/焦段，再重跑 `studio`；产品台半径用 `AI3D_PLINTH_R=0.2` 这类环境变量临时缩。`camera01` 用的还是头盔的构图，所以留白偏多，但流程本身没改。

---

### 4.9 电影感海报变体（可选）

**做什么**：保留 4K 母版，把图缩到 1536 宽，交给 Qwen 图像编辑换背景、加雾气、点亮视缝，做一张电影感变体。**它不替代 4K 母版。**

**怎么敲**：

```bash
# 先缩图（Pillow 在 ComfyUI venv 里）
~/ComfyUI/venv/bin/python - <<'PY'
from PIL import Image
im = Image.open('/home/roland/ai3d/renders/helmet01_4k.png')
im.thumbnail((1536, 1536), Image.LANCZOS)
out = '/home/roland/ai3d/renders/helmet01_poster_input.png'
im.convert('RGB').save(out)
print(im.size, out)
PY

python3 ~/ai3d/scripts/comfy_run.py edit \
  --image ~/ai3d/renders/helmet01_poster_input.png \
  --prompt "Keep the metal helmet, its pose, proportions and panel details unchanged. Replace the studio background with a dark futuristic hangar: cold blue volumetric light beams from above, thin ground fog, floating dust particles, subtle warm orange emergency light on the left, glossy dark floor with soft reflections. Add a faint cyan glow inside the horizontal visor slit. Cinematic sci-fi movie poster lighting, dramatic contrast, ultra detailed, no text, no letters, no watermark." \
  --seed 777 --resolution 1536 \
  --outdir ~/ai3d/renders \
  --name helmet01_poster_edit_2k.png
```

**怎么算成功**：

- `helmet01_poster_edit_2k.png` 是 2048×1152、约 3MB
- 头盔仍是 3/4 视角、单件、没有乱加文字；背景有冷蓝体积光、薄雾、左侧暖橙光
- 本机实测：`--resolution 1536` 用 164 秒；`--resolution 1024` 用 66 秒，输出 1376×768
- `renders/run_edit_*.json` 里有这次编辑的 prompt、seed、prompt_id、耗时

**失败查哪**：

- OOM：把 `--resolution` 降到 1024；这条链路比文生图更吃显存。
- 头盔细节被改：这是图生图的正常偏差。提示词里继续强调 `keep ... unchanged`，换 seed；不要拿它当母版。
- 加了文字/logo：cfg=1 时 negative prompt 不生效，直接换 seed 重跑。
- 想要真正可排版的标题：在变体图上方留出负空间（提示词写 `deep black negative space on the left for a title`），再用设计工具压字；不要指望模型把中文字排对。

### 4.10 拆成可编辑部件（可选，dragon01 范例）

**做什么**：AI 重建出来的龙、兽、角色常常是“一张皮”：角、须、爪和身体粘在同一个网格里，整体重网格化也分不开。`25_parts.py` 用“种子 + 测地线生长”或“胶囊折线”在表面上认领区域，把整块网格拆成多个独立对象。dragon01 已拆成 9 件：龙身、龙头、龙角、鬃毛、2 根龙须、3 只爪。

**为什么不选 Hy3D Instant-Meshes Remesh**：它主要解决减面/面片排布，不做语义分件；而且我们实测的版本没有把新拓扑交回场景，还会丢 UV/顶点色。分件和重网格化是两件事，先把件分开，再按需对单件重拓扑，顺序才对。

**怎么敲**：

```bash
# 分件（读源 .blend，产物写到 projects/dragon01/parts/，不覆盖源文件）
~/.local/bin/blender -b ~/ai3d/blend/dragon01.blend \
  --python ~/ai3d/scripts/blender/25_parts.py -- \
  --config ~/ai3d/projects/dragon01/parts.json

# 预览：组装图 + 爆炸图 + 9 张单件图
~/.local/bin/blender -b ~/ai3d/projects/dragon01/parts/dragon01_parts.blend \
  --python ~/ai3d/scripts/blender/27_parts_preview.py -- \
  --config ~/ai3d/projects/dragon01/parts.json \
  --out ~/ai3d/projects/dragon01/parts/preview

# 九宫格验收板
python3 ~/ai3d/scripts/blender/28_parts_sheet.py \
  --manifest ~/ai3d/projects/dragon01/parts/parts_manifest.json \
  --cells ~/ai3d/projects/dragon01/parts/preview/cells \
  --out ~/ai3d/projects/dragon01/parts/preview/dragon01_parts_sheet.png

# 重新导入 GLB 验网格数、原点、材质
~/.local/bin/blender -b --python ~/ai3d/scripts/blender/29_verify_parts_glb.py -- \
  --glb ~/ai3d/projects/dragon01/parts/glb/dragon01_parts.glb \
  --parts-dir ~/ai3d/projects/dragon01/parts/glb --expect 9
```

**怎么算成功**：

- 第 1 条以 `[OK] 分件完成：9 件` 结尾，生成 `parts/dragon01_parts.blend`、`parts_manifest.json` 和 `glb/` 下 1 个组合 GLB + 9 个单件 GLB。
- 打开 `parts/dragon01_parts.blend`，集合 `dragon01_Parts` 里正好 9 个 `Dragon_*` 网格；源龙 `dragon01_model` 隐藏保留；每个单件原点在自己包围盒中心。
- 第 4 条以 `[OK] 验收通过` 结尾：组合 GLB 9 个网格、249,704 个三角面，单件原点 `(0,0,0)`、材质 `Dragon_Bronze` 都在。
- 九宫格是 1900×1778，9 件都有中文名和面数。

**失败查哪**：

- `找不到 source_object`：配置里的 `source_object` 必须和源文件里的网格名一致；dragon01 是 `dragon01_model`。
- 某个部件没分到面：调大 `radius_m` 或改 `seeds`；细长部位用 `capsule`，别用球。先加 `--print-fps 32` 挑点，再用 `--dry-run` 看面数。
- 预览黑图/空帧：确认打开的是 `parts/dragon01_parts.blend`，不是源文件；预览脚本会自己切 Workbench。
- 切口是开放边：源网格有 15,740 条非流形边，补洞只能尽力而为。`solidify_mm` 可以加厚，但实测 1.2 mm 会出现边缘毛刺，不保证水密，打印前仍需修模。
- 更多参数、已知限制和后续重拓扑方案：见 `projects/dragon01/parts/README.md`。

> 这套分件脚本是配置驱动的，换模型时复制一份 `parts.json`，改 `source_object` 和种子即可。源文件始终只读，所有产物写在项目自己的 `parts/` 目录。

### 4.11 给分件模型装第一版骨架（可选，dragon01 范例）

**做什么**：给 9 个部件装 14 根骨，能摆姿势、能导出带蒙皮的 GLB。这不是最终动画骨架：`body` 是一整根骨，**身体暂时不能沿脊柱弯曲**；头、角、鬃毛、3 只爪、2 根龙须可以各自动。为什么不做脊柱、切口和龙须缺口怎么处理，见 `projects/dragon01/rig/README.md`。

这一阶段已经接进流水线：`projects/dragon01/rig.json` 描述部件、骨头、权重、姿态和验收规则；`scripts/blender/run_rig.py` 按顺序跑 32 → 35 → 33 → 34，最后写两份机器可读报告。换模型时改配置，不用复制脚本。

**怎么敲**：

```bash
cd ~/ai3d

# 一条命令：建骨 → GLB 验收 → 姿势预览 → 验收板
python3 scripts/blender/run_rig.py --project dragon01

# 只想先看会执行什么，不真跑
python3 scripts/blender/run_rig.py --project dragon01 --dry-run
```

跑完生成/覆盖：

- `rig/dragon01_rig.blend`：主工程，休息姿势；
- `rig/rig_manifest.json`：骨树、每个件的绑定方式、验收测试表；
- `rig/glb/dragon01_rig.glb`：带蒙皮的 GLB；
- `rig/preview/rig_*.png` + `dragon01_rig_sheet.png`：预览和验收板；
- `rig/verify_report.json` + `rig/rig_report.json`：机器验收和流水线汇总。

分步跑（某一步失败时排查用）：

```bash
# 1) 搭骨架 + 绑定 + 导出 GLB（读分件工程，写 rig/，不覆盖源文件）
~/.local/bin/blender -b projects/dragon01/parts/dragon01_parts.blend \
  --python scripts/blender/32_rig_parts.py -- \
  --config projects/dragon01/rig.json \
  --out projects/dragon01/rig

# 2) 重新导入 GLB，验 skin/骨数/权重/变形，并写报告
~/.local/bin/blender -b --python scripts/blender/35_verify_rig_glb.py -- \
  --glb projects/dragon01/rig/glb/dragon01_rig.glb \
  --manifest projects/dragon01/rig/rig_manifest.json \
  --report projects/dragon01/rig/verify_report.json

# 3) 摆动作姿势，渲染 5 张预览（不保存 .blend）
~/.local/bin/blender -b projects/dragon01/rig/dragon01_rig.blend \
  --python scripts/blender/33_rig_pose.py -- \
  --manifest projects/dragon01/rig/rig_manifest.json \
  --out projects/dragon01/rig/preview --res 1400

# 4) 拼 2×2 验收板
python3 scripts/blender/34_rig_sheet.py \
  --config projects/dragon01/rig.json \
  --manifest projects/dragon01/rig/rig_manifest.json \
  --preview projects/dragon01/rig/preview \
  --out projects/dragon01/rig/preview/dragon01_rig_sheet.png
```

**怎么算成功**：

- 一键命令以 `[OK] 绑定流水线完成：4 步` 结尾，下面列出主工程、GLB、清单、验收板、报告五个路径；本机正常约 12–20 秒。
- `rig/rig_report.json` 里 `"ok": true`，`steps` 四步都是 `"ok": true`；`rig/verify_report.json` 的三组 `pose_tests` 也都 `"ok": true`。
- 第 1 条日志里是 14 根骨、9 个件；身体权重是 `56552 顶点纯 body，26200 顶点带渐变`。
- 第 2 条以 `[OK] 绑定验收通过：14.7 MB / 249,708 三角面 / 9 网格 / 14 骨 / 权重和=1` 结尾；转头 25° 时龙头位移 40.4 mm、鬃毛 0 mm，转爪 20° 时爪 14.1 mm、腿根身体 9.4 mm。
- 第 3 条生成 `rig_rest.png`、`rig_pose_3q.png`、`rig_pose_front.png`、`rig_pose_side.png`、`rig_pose_head.png`，透明背景。
- 第 4 条输出 `1604x1960` 的验收板，四格都有图。
- `projects/dragon01/run.json` 的 `stages` 里会出现 `rig`、`rig-verify`、`rig-pose` 三个阶段记录。

**失败查哪**：

- `[×] 找不到骨架配置 .../rig.json`：配置文件丢了；从本项目复制一份 `rig.json`，或检查 `AI3D_RIG_CONFIG`。
- `[×] 当前场景只有部分件，缺少 [...]`：`rig.json` 里的 `rigid` / `whiskers` 件名和分件工程对不上；先用 `parts/parts_manifest.json` 核对名字。
- 一键脚本中途停下：终端会写 `第「某步」步失败`，并给一句先查什么；打开 `rig/rig_report.json` 看 `failed_step`、`hint` 和该步退出码，前面的步骤不会白跑。
- 姿势表里的骨头不存在：`rig.json` 的 `preview.pose` 或 `verify.pose_tests` 写错了骨名；骨名以 `rig_manifest.json` 的 `bones[]` 为准。
- 找不到 `Dragon_Rig`：打开的是分件工程，不是 `rig/dragon01_rig.blend`。
- 骨架被网格挡住：选中 `Dragon_Rig`，在 Object Data Properties → Viewport Display 勾 In Front；或 `Alt+H` 取消隐藏。
- 转骨网格不动：没进 Pose Mode，或在 Object Mode 转了整个对象。
- 头转鬃毛也动：旧工程；重跑一键命令，`mane` 的父级应该是 `body`。
- 转头看到颈切口内壁、龙须根部有断口：这是源网格的开放薄壳/两个岛，不是绑定失败；限制与修法见 `projects/dragon01/rig/README.md` 第 6、7 节。
- 验收板缺图、PIL 报错：先跑姿势预览；`run_rig.py` 会自动找带 Pillow 的 Python，找不到就显式传 `--python ~/ComfyUI/venv/bin/python`。
- 身体不能弯：v1 的设计；要弯身体先重拓扑 + 展 UV + 加脊柱骨链，不要直接上动画。

> 换模型时复制 `projects/<名字>/rig.json`，改 `source_blend`、`parts_config`、`rigid`、`whiskers`、`preview.pose`、`verify.pose_tests` 和 `file_stem` 即可；脚本本身不再写死龙的部件名。配置里的相对路径以 `rig.json` 所在目录为基准，把配置挪到别处试验时请改成绝对路径。当前只在 dragon01 上实测过，新模型的件数/骨数可以不同，但仍属于“部件级”绑定，不是脊柱蒙皮。在 Blender MCP 里也可以设 `AI3D_STAGE=rig` / `rig-pose` / `rig-verify` 分阶段调用，环境变量见 `run_stage.py` 顶部。

---

## 5. 换一个题材

以「复古相机」为例：

```bash
~/ai3d/scripts/new_project.sh camera01
# 编辑 ~/ai3d/prompts/camera01_concept.txt
~/ai3d/scripts/gen_concepts.sh camera01
```

然后重复 4.5–4.8，把项目名换成 `camera01`。

`camera01` 已经用同一套脚本跑完：2 张概念图 → 编辑成纯白 → 出模 → Blender 导入/清理/材质/摄影棚，预览在 `~/ai3d/renders/camera01_preview.png`。相机的刻度、旋钮这类薄细节会比头盔软，这是 Hunyuan 单图重建的上限；流程不用改。第一版没纯白化时，地面淡阴影被烘成一块薄板（`camera01/refs/hy_input.png` 是那次输入，`model_shadow_bad.glb` 是失败样本），纯白化后才正常。

**提示词的五条铁律：**

1. **单件**：`a single standalone ...`，不要写「一套」「一组」。
2. **完整入画**：`complete object fully inside the frame with clean empty margin`。
3. **纯白背景**：`pure white seamless background`，不要复杂场景；出图后跑 `whiten_bg.py`。
4. **3/4 视角 + 硬表面**：`three-quarter front view, hard-surface industrial design`。
5. **不要地面阴影/倒影**：写 `no floor shadow, no reflection`；Hunyuan 会把淡阴影烘成真实几何。

**适合的题材**：头盔、面具、枪械、相机、音箱、机器人头/手、载具零件、鞋（硬底）、手表、工具。
**不适合的题材**：人脸、全身角色、手指、布料、毛发、透明玻璃杯、细长悬空结构。

### 5.1 曲面题材：中国龙（dragon01）

龙、兽、人物这类曲面体，Hunyuan 重建出来的网格通常“形体对、表面光”，鳞片和褶皱会被抹平。`dragon01` 的解法是**把选中的概念图正面投影回模型**，同时当颜色贴图和凹凸贴图用。

已跑完的成品：4K 海报 `~/ai3d/renders/dragon01_4k.png`、GLB `~/ai3d/projects/dragon01/model.glb`、工程 `~/ai3d/blend/dragon01.blend`。

关键做法：

- 概念图要求龙“盘成紧凑 3D 螺旋、头在前、四肢抓盘体”。长条形的龙单视图重建很容易断，盘龙能把四面八方的形体压进一张图里。
- 输入 Hunyuan 前仍要纯白化（本次自动涂白 74.5%）。
- `materials` 阶段会读 `projects/dragon01/refs/dragon_tex_meta.json` 里的图片 bbox，把模型正面 XZ 投影成一个叫 `AI3D_Front` 的 UV 层，再加载同目录的 `dragon_albedo.png`（颜色）和 `dragon_height.png`（高度/凹凸）。贴图缺失时会自动退回纯程序化材质，不会把流程卡死。
- 颜色贴图只以 0.32 的比例混进程序化青铜底色，并乘一层暖金 tint，避免概念图的银白高光直接变成“镀铬龙”。
- 投影的副作用：模型侧面和背面会分到正面的拉伸纹理。静态海报不明显；如果要 360° 环拍，得老老实实展 UV + 烘焙。

切换龙的摄影棚 / 材质，只要在跑阶段脚本前加环境变量：

```python
import os
os.environ["AI3D_PROJECT"] = "dragon01"
os.environ["AI3D_LOOK"] = "dragon"      # 龙材质 + 黑底红晕 + 龙珠
os.environ["AI3D_STAGE"] = "studio"     # import / clean / materials / studio / render
exec(open("/home/roland/ai3d/scripts/blender/run_stage.py").read())
```

龙专用开关：`AI3D_PEARL=0` 去掉悬浮龙珠，`AI3D_RING=0` 去掉金色发光环，`AI3D_PLINTH_R=0.12` 改台座半径。本次实测：25 万三角面、GLB 5.10MB、预览 9 秒、4K（3840×2160 / 128 samples / 16-bit）50 秒。

---

## 6. 复现：run.json 和 seed

每次 `comfy_run.py` 都会写 `run_<mode>_<时间>.json`，里面有：

- `mode`、`prompt`、`negative`、`seed`、`batch`
- `steps`、`cfg`、`models`（UNET/CLIP/VAE/Checkpoint 文件名）
- `comfyui_version`、`prompt_id`、`started_at`、`elapsed_sec`
- 输入图的 sha256
- 每个输出文件的路径、字节数、sha256

`projects/<name>/run.json` 是总账：Blender 各阶段耗时与网格统计、5 盏灯和相机、最终渲染参数、四个权重的 sha256，以及本项目所有 ComfyUI manifest 的路径。换机器复现时，**先核对 run.json 里的权重 sha256**，再看 seed。

想复现某张图：

1. 打开对应的 `run_t2i_*.json`，抄下 `prompt` 和 `seed`。
2. 用同样的 `--prompt`、`--seed` 跑 `comfy_run.py t2i`。
3. 同一个 ComfyUI 版本 + 同一份权重 + 同一个 seed，输出应当一致；换显卡/驱动/ComfyUI 版本可能有细微差别。

Blender 端的可复现性靠 `.blend` 本身：所有材质参数、灯光、相机都在工程里，不依赖外部贴图（贴花除外）。

---

## 7. 故障表

| 症状 | 可能原因 | 处理 |
|---|---|---|
| ComfyUI 启动报 `IMPORT FAILED` | 自定义节点与 0.42.1 不兼容 | 无自定义节点冒烟：`./venv/bin/python main.py --port 8189 --disable-all-custom-nodes`；把报错节点移到 `~/ai3d/backups/custom_nodes/` |
| 提交 prompt 返回 400/节点错误 | 工作流里的模型文件名不存在 | 看返回 JSON 的 `node_errors`；跑 `check_env.sh` 对文件名 |
| Qwen OOM | 1024 也吃紧，或 Blender 同时渲染 | 关 Blender 渲染；`--batch 1`；作业间 `/free`；`--reserve-vram 0.6`；换 w4a8 文本编码器 |
| Qwen 黑图 | VAE/权重不对，或 cfg/采样器被改 | 三个加载器都指向 UC 三件套；steps 25、cfg 1.0、euler/simple |
| Qwen 编辑不参考输入图 | `images.image_1` 没接，或 latent 接错 | 对照 `qwen_edit.json`：LoadImage→`images.image_1`，KSampler latent←TextEncode 第 3 输出 |
| Hunyuan GLB 很小/空 | 输入图背景脏、物体被裁、多物体 | 回 4.5 清图；阈值 0.55–0.65；用本次新文件 |
| Hunyuan 输出一块薄板/大底座 | 输入背景不是纯白，淡阴影被当成几何 | 跑 `whiten_bg.py` 后重出模；或在 Blender 里删 z≈0 的大平面 |
| Hunyuan 出模缺一半 | 输入是转身表或物体不完整 | 单视图、完整入画；换 seed/换图 |
| Blender 导入没面 | GLB 损坏或只有点云 | `stat` 看大小；重新出模；`get_scene_info` 看面数 |
| 模型尺寸不对 | 归一化没跑或 GLB 单位异常 | 重跑 `import`；看打印的尺寸；用 `AI3D_SIZE` 改目标 |
| 渲染全黑 | 相机在模型里/灯光关了/曝光错 | 先跑 preview；检查相机位置和 5 盏灯；AgX 曝光回 0 |
| 渲染异常慢 | OptiX 没启用 / 在跑 CPU / 掉卡 | 本机 4K 正常约 1 分钟；超过 3 分钟先看日志里的设备名和 `nvidia-smi`，别直接加 samples |
| CUDA error / 掉卡 | 本机 PCIe 掉卡史 | `nvidia-smi` 查 Xid；crashcam 保持运行；重跑；连续失败降分辨率或 Cycles CPU |
| MCP 9876 拒绝连接 | Blender 没开 / 插件没启动 | 重启 Blender；Preferences → Add-ons → Blender MCP → Start MCP Server |
| MCP 调用超时 | 4K 渲染/大操作阻塞 | 最终渲染走 CLI；MCP 只做建模和预览 |
| 下载 0 字节/卡住 | hf-mirror 连接问题 | `HF_ENDPOINT=https://hf-mirror.com`、`HF_HUB_DISABLE_XET=1`、`curl -C -` 续传；核对字节数 |
| 磁盘满 | 下载 + 输出 + 备份 | `df -h ~`；移到外置盘；删旧 renders |

---

## 8. 回滚 ComfyUI

只有确认 0.42.1 把某个你必须用的插件弄坏了才回滚。

```bash
# 1. 停掉 ComfyUI（前台 Ctrl+C；后台找 PID）
pkill -f 'ComfyUI/main.py' || true

# 2. 恢复 venv
cd ~/ComfyUI
rm -rf venv
cp -a ~/ai3d/backups/venv-0.33 venv

# 3. 回到升级前的分支
git checkout backup/pre-qwen-20261020
git status --short

# 4. 恢复启动脚本
cp ~/ai3d/backups/start.sh.pre-ai3d ~/ComfyUI/start.sh

# 5. 重新启动
./start.sh
```

回滚后 Qwen-Image 2.1 的节点会消失，但 Hunyuan3D 2.1 的节点在 0.33 里本来就有。想再升回来：`git checkout qwen21`，重装依赖，参考 P0 的命令。

> 回滚前先备份当前 `venv` 和 `start.sh`，否则来回切会丢配置。

---

## 9. 时间与空间预算

| 环节 | 首次 | 之后每件作品（helmet01 实测） |
|---|---|---|
| 升级 + 下载 + 校验 | 1.5–2 小时 | — |
| Qwen 4 张概念图 | 10–20 分钟 | 约 4 分钟（52–56 秒/张） |
| Qwen 清背景 / 图像编辑 | 2–5 分钟 | 66 秒（1024）；164 秒（1536） |
| Hunyuan 出模 | 3–8 分钟 | 73 秒（9.36MB GLB，52.7 万三角面） |
| Blender 清理 / 材质 / 打光 | 20–40 分钟 | 20–60 分钟（主要花在调外观） |
| 1K 预览 | 20–60 秒 | 9 秒 |
| 4K 渲染 | 10–25 分钟 | 61–63 秒（128 samples，16-bit） |
| **合计** | **约 1.5–2 天** | **约 1.5–3 小时** |

空间：权重 24.3GB；每个项目 1–3GB（GLB + blend + 渲染 + 中间图）。

---

## 10. 本期不做

- Hunyuan3D 2.0 多视图
- 角色绑定 / 动画
- 游戏级重拓扑、UV、LOD
- 3D 打印水密处理
- 纹理烘焙（Hunyuan 的原生纹理管线需要额外大模型，本期不引入）

这些等通用模板跑顺后再单独立项。

---

## 11. 许可与合规（请认真读）

- **Qwen-Image 2.1 / UC 量化版**：仓库元数据是 **Qwen Research License**，仅限研究与非商用。即使名字里有 "Uncensored"，许可证没有变。模型无内容过滤器，输出由使用者负责。
- **Hunyuan3D 2.1**：**Tencent Hunyuan 3D 2.1 Community License**。商业使用受 MAU 和地区限制；使用前读官方 LICENSE 原文。不要凭「开源」二字直接商用。
- **Blender**：GPL；你用 Blender 做出的作品归你，但分发 Blender 本身要遵守 GPL。
- **不要**用本流水线生成违法、侵权、冒充他人、虚假信息或 deceptive 内容。
- 公开作品建议标注：`Made with Qwen-Image 2.1 (research license) + Hunyuan3D 2.1 + Blender`。

---

## 12. 命令速查

```bash
# 自检
~/ai3d/scripts/check_env.sh

# 启动 ComfyUI
cd ~/ComfyUI && ./start.sh

# 下载 + 校验
~/ai3d/scripts/download_weights.sh
~/ai3d/scripts/finalize_weights.sh

# 新项目 / 4 张概念图
~/ai3d/scripts/new_project.sh camera01
~/ai3d/scripts/gen_concepts.sh camera01

# 清背景
python3 ~/ai3d/scripts/comfy_run.py edit --image .../chosen.png \
  --prompt "$(cat ~/ai3d/prompts/helmet01_clean.txt)" --seed 1201 \
  --outdir .../refs --name hy_input.png

# 背景纯白化（强烈建议，避免阴影被烘成薄板）
~/ComfyUI/venv/bin/python ~/ai3d/scripts/whiten_bg.py \
  .../refs/hy_input.png .../refs/hy_input_white.png

# 出模
python3 ~/ai3d/scripts/comfy_run.py hy3d --image .../hy_input.png \
  --outdir ~/ai3d/projects/helmet01 --name model.glb

# Blender 阶段（Qoder / Blender Python Console）
import os
os.environ["AI3D_PROJECT"]="helmet01"; os.environ["AI3D_STAGE"]="import"
exec(open("/home/roland/ai3d/scripts/blender/run_stage.py").read())

# 预览 / 4K
~/ai3d/scripts/render_final.sh helmet01 preview
~/ai3d/scripts/render_final.sh helmet01

# 分件（以 dragon01 为例；参数与限制见 projects/dragon01/parts/README.md）
~/.local/bin/blender -b ~/ai3d/blend/dragon01.blend \
  --python ~/ai3d/scripts/blender/25_parts.py -- \
  --config ~/ai3d/projects/dragon01/parts.json
~/.local/bin/blender -b ~/ai3d/projects/dragon01/parts/dragon01_parts.blend \
  --python ~/ai3d/scripts/blender/27_parts_preview.py -- \
  --config ~/ai3d/projects/dragon01/parts.json \
  --out ~/ai3d/projects/dragon01/parts/preview
python3 ~/ai3d/scripts/blender/28_parts_sheet.py \
  --manifest ~/ai3d/projects/dragon01/parts/parts_manifest.json \
  --cells ~/ai3d/projects/dragon01/parts/preview/cells \
  --out ~/ai3d/projects/dragon01/parts/preview/dragon01_parts_sheet.png
~/.local/bin/blender -b --python ~/ai3d/scripts/blender/29_verify_parts_glb.py -- \
  --glb ~/ai3d/projects/dragon01/parts/glb/dragon01_parts.glb \
  --parts-dir ~/ai3d/projects/dragon01/parts/glb --expect 9

# 绑定（部件级 v1；一条命令跑完骨架→验收→预览→验收板）
python3 ~/ai3d/scripts/blender/run_rig.py --project dragon01

# 只重建骨架，或只复检已有 GLB
python3 ~/ai3d/scripts/blender/run_rig.py --project dragon01 --build-only
python3 ~/ai3d/scripts/blender/run_rig.py --project dragon01 --verify-only

# 看日志
tail -f ~/ai3d/logs/comfyui.log
tail -f ~/ai3d/logs/render_helmet01_*.log
```
