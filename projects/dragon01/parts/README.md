# 中国龙分件（dragon01）

一句话：原来是一整块、粘在一起的中国龙，现在按语义拆成了 **9 个独立网格**。角、须、爪都能单独选中、移动、旋转、雕刻、导出，源文件没有被覆盖。

这份文档是给第一次接触 Blender 分件的人写的。每一步都按四拍走：**做什么 / 怎么敲 / 怎么算成功 / 失败查哪**。

---

## 0. 先说结论：为什么不用 Hy3D Instant-Meshes Remesh

你最初的问题是“只有一层 mesh，无法后续调整”。这里其实是两个问题，要分开看：

1. **重网格化（remesh / retopo）**：把三角面重新排成更整齐的面。它能让表面更好雕刻，但**不会**把粘在一起的身体、角、须分开。
2. **分件（segmentation）**：先判断“哪些面属于角、哪些属于须”，再把它们拆成独立对象。这一步和面片排布无关。

我们检查了流水线里的 **Hy3D Instant-Meshes Remesh**（`Hy3DIMRemesh` / `Hy3D21IMRemesh`）：

- 它的强项是减面，不是语义分件。
- 在我们实际跑的版本里，节点算完新顶点/面后，场景里拿到的仍是原对象的拷贝；超过 `max_facenum` 时只做减面。
- 它会把 UV 和顶点颜色丢掉，而这条龙依赖 `AI3D_Front` UV 和投影贴图。
- 就算它交回了新拓扑，角、须、爪仍然是连在身体上的同一张面，问题没解决。

所以推荐的顺序是：

> **先按语义分件 → 需要时再对单个部件做重拓扑 / 加厚 / 修洞。**

本次交付的是第一步。第二步留了明确的入口，见第 7 节。

另外要诚实说清楚：这条龙的源网格有 **15,740 条非流形边**，是一张很薄的 AI 生成曲面，不是实体。分件解决了“不能单独调”的问题，但没有把它变成水密实体。切口目前是开放边，打印前还要处理。

---

## 1. 这次交付了什么

### 1.1 九个部件

| 部件 | 中文名 | 源面数 | 说明 |
|---|---|---:|---|
| `Dragon_Body` | 龙身 | 171,023 | 兜底部：没被其他部件认领的面都归它 |
| `Dragon_Head` | 龙头 | 32,199 | 含面部、嘴部附近；边界是近似分割 |
| `Dragon_Antlers` | 龙角 | 10,123 | 三处角，保护标签不被平滑吃掉 |
| `Dragon_Mane` | 鬃毛 | 16,479 | 头后飘动的鬃毛 |
| `Dragon_Whisker_A` | 前垂龙须 | 1,779 | 用胶囊折线抓取；内部有 2 个岛 |
| `Dragon_Whisker_B` | 右侧龙须 | 1,003 | 用种子 + 测地线抓取 |
| `Dragon_Leg_A` | 右上爪 | 6,132 | 含爪 |
| `Dragon_Leg_B` | 腹前爪 | 4,073 | 含爪 |
| `Dragon_Leg_C` | 左下爪 | 6,602 | 含爪 |

表里加起来是 249,413 个源面；导出 GLB 时会三角化，组合 GLB 里实测是 **249,704 个三角面**，和源网格的 249,999 面基本一致。分件时丢弃了少量零碎小岛（每个部件 0–538 面），同时补洞又添了一点面；明细在 `parts_manifest.json` 的 `island_report` 里。

### 1.2 文件在哪、各自干什么

| 文件 | 大小 | 用途 |
|---|---:|---|
| `dragon01_parts.blend` | 38 MB | **主工程**。打开就能看到 9 个部件，源龙已隐藏 |
| `parts_manifest.json` | 14 KB | 分件参数、种子、每个部件的 QA 数字；排查问题先看它 |
| `glb/dragon01_parts.glb` | 11 MB | 组合版：9 个网格保持原位置，适合整体预览 |
| `glb/Dragon_*.glb` | 3–9 MB | 9 个单件，每个原点在自己的包围盒中心，适合单独编辑/换装/进引擎 |
| `preview/dragon01_parts_sheet.png` | 1.3 MB | 九宫格验收板，带中文名、面数、颜色 |
| `preview/dragon01_parts_assembled.png` | 2.1 MB | 组装状态渲染 |
| `preview/dragon01_parts_exploded.png` | 1.9 MB | 爆炸图，能看清 9 件的相对位置 |
| `preview/cells/Dragon_*.png` | 1.5–1.9 MB | 每个部件的单独渲染，拼验收板用 |

主工程里的组织方式：

- 9 个部件放在集合 `dragon01_Parts` 里，统一父级到空物体 `dragon01_Parts_Root`。
- 每个部件的原点在自己的包围盒中心，所以旋转时绕自己转，不会绕世界原点甩出去。
- 源对象 `dragon01_model` 还在文件里，但在视口和渲染里都隐藏了，作为对照和回退。
- 摄影棚（`AI3D_STUDIO` 集合：台座、龙珠、灯、相机）在视口里默认隐藏，避免挡住部件；渲染开关没动，需要时在 Outliner 点它的显示器图标恢复。
- 颜色是 **Blender 视口颜色**，只用于区分部件；GLB 里 9 个件共用原来的 `Dragon_Bronze` 材质，没有拆成 9 套材质。

---

## 2. 三十秒验收

**做什么**：确认图、工程、GLB 三样都能打开，且确实是 9 件。

**怎么敲**：

```bash
# 1) 先看验收板（双击也行）
xdg-open /home/roland/ai3d/projects/dragon01/parts/preview/dragon01_parts_sheet.png

# 2) 打开主工程
~/.local/bin/blender /home/roland/ai3d/projects/dragon01/parts/dragon01_parts.blend

# 3) 重新导入 GLB 做机器验收
cd /home/roland/ai3d
~/.local/bin/blender -b --python scripts/blender/29_verify_parts_glb.py -- \
  --glb projects/dragon01/parts/glb/dragon01_parts.glb \
  --parts-dir projects/dragon01/parts/glb \
  --expect 9
```

**怎么算成功**：

- 验收板是 1900×1778，九宫格里 9 个部件都有图、有中文名、有面数。
- Blender 打开后，大纲视图里能看到 `dragon01_Parts` 集合和 9 个 `Dragon_*` 对象；源对象 `dragon01_model` 是隐藏的。
- 最后一条命令以 `[OK] 验收通过` 结尾，并且打印：
  - 组合 GLB：9 个网格，249,704 面，根对象 `dragon01_Parts_Root`
  - 每个单件的原点都是 `(0, 0, 0)`
  - 每个单件都还有 `Dragon_Bronze` 材质

**失败查哪**：

- 图片打不开：先确认路径；本机图片查看器是 `xdg-open`，没有桌面环境时用文件管理器打开。
- Blender 打开是空场景：检查是不是打开了 `blend/dragon01.blend`（源文件）而不是 `parts/dragon01_parts.blend`。
- 验收提示网格数不对：不要手工改过 `glb/` 里的文件；回到第 4 节重跑。
- 验收提示原点不是 0：检查是否用了 `--no-export` 或改过 `export_parts_centered`；重新导出即可。

---

## 3. 在 Blender 里单独调整一个部件

**做什么**：选中一个部件，单独移动、旋转、缩放，或者进入编辑模式改网格。

**怎么敲**：

1. 打开 `dragon01_parts.blend`。
2. 在右上角大纲视图（Outliner）展开 `dragon01_Parts`，点选比如 `Dragon_Antlers`。
3. 如果看到台座、龙珠或灯光挡住视线：在 Outliner 里点 `AI3D_STUDIO` 旁边的显示器图标，把整个摄影棚集合关掉（它默认是隐藏的，重跑分件后可能恢复显示）。
4. 在 3D 视口按 `Numpad /`（小键盘斜杠）进入“局部视图”，其他部件会暂时隐藏。没有小键盘就用菜单 **View → Local View → Toggle Local View**。
5. 按 `G` 移动、`R` 旋转、`S` 缩放；按 `Tab` 进编辑模式改点/线/面。
6. 想恢复全局视图，再按一次 `Numpad /`。

如果只想看颜色区分：把视口右上角的着色方式切成 **Workbench**，再把 `Color` 设成 **Object**。这就是预览图的效果。

**怎么算成功**：

- 大纲里只有一个部件被选中，其他部件不受影响。
- 旋转时部件绕自己的中心转，不是绕整个场景的世界原点转。
- 移动后切回全局视图，部件和身体的接缝位置符合预期。

**失败查哪**：

- 一选就选中了整条龙：你选到了 `dragon01_Parts_Root` 空物体，改选下面的 `Dragon_*` 网格。
- 旋转时飞到很远：确认选的是部件对象而不是父级空物体；部件的原点应该在自身包围盒中心。
- 颜色全是灰的：着色方式不是 Workbench + Object，或者材质预览覆盖了对象颜色。
- 改坏了想重来：不要覆盖源文件；关掉不保存，重新打开 `dragon01_parts.blend`。源文件 `blend/dragon01.blend` 始终没动。

> 注意：切开的边缘是开放边，编辑模式里能看到一圈“没有面”的边界。这是正常的，不代表文件坏了。要补成实体见第 6 节。

---

## 4. 从头重跑分件流水线

**做什么**：改分件参数或换模型后，重新生成 9 个部件、预览图和 GLB。

**怎么敲**（在 `/home/roland/ai3d` 下执行）：

```bash
# 1) 分件：打开源龙，生成 parts/dragon01_parts.blend、manifest、GLB
~/.local/bin/blender -b /home/roland/ai3d/blend/dragon01.blend \
  --python scripts/blender/25_parts.py -- \
  --config /home/roland/ai3d/projects/dragon01/parts.json

# 2) 渲染组装图、爆炸图、9 张单件图
~/.local/bin/blender -b projects/dragon01/parts/dragon01_parts.blend \
  --python scripts/blender/27_parts_preview.py -- \
  --config projects/dragon01/parts.json \
  --out projects/dragon01/parts/preview

# 3) 拼九宫格验收板（用系统 Python + Pillow，不需要 Blender）
python3 scripts/blender/28_parts_sheet.py \
  --manifest projects/dragon01/parts/parts_manifest.json \
  --cells projects/dragon01/parts/preview/cells \
  --out projects/dragon01/parts/preview/dragon01_parts_sheet.png

# 4) 重新导入 GLB 验收
~/.local/bin/blender -b --python scripts/blender/29_verify_parts_glb.py -- \
  --glb projects/dragon01/parts/glb/dragon01_parts.glb \
  --parts-dir projects/dragon01/parts/glb \
  --expect 9
```

**怎么算成功**：

- 第 1 条最后打印 `[OK] 分件完成：9 件`，并写出 `parts/dragon01_parts.blend`。
- 第 2 条最后打印 `完成`，`preview/` 下三张图和 `preview/cells/` 九张图的时间戳都更新。
- 第 3 条打印 `已写 .../dragon01_parts_sheet.png (1900x1778)`。
- 第 4 条打印 `[OK] 验收通过`。
- 源文件 `blend/dragon01.blend` 的修改时间不变。

**失败查哪**：

- `找不到配置文件`：`--config` 要用绝对路径，或者确认 `projects/dragon01/parts.json` 存在。
- `找不到 source_object`：配置里的 `source_object` 必须和源 .blend 里的网格对象名完全一致；当前是 `dragon01_model`。
- 预览是全黑/空帧：确认打开的是 `parts/dragon01_parts.blend`；脚本会自己切 Workbench，不需要显卡。
- 九宫格有空格子：先看 `preview/cells/` 里对应文件是否存在；缺图通常是第 2 步没跑完。
- 验收网格数不是 9：看第 1 步日志里有没有 `⚠`；某个部件可能因为半径太小没有分到面，或小岛被丢弃。
- 改完配置但结果没变：确认命令里的 `--config` 指向你改的那个文件，且 Blender 进程已退出。

### 只调试种子，不生成文件

```bash
~/.local/bin/blender -b /home/roland/ai3d/blend/dragon01.blend \
  --python scripts/blender/25_parts.py -- \
  --config /home/roland/ai3d/projects/dragon01/parts.json \
  --print-fps 32
```

它会在 `parts/fps_points.json` 里写 32 个最远点采样坐标（单位米），用来挑种子。`--dry-run` 只算分件和统计，不建对象、不写文件；`--no-export` 不写 GLB；`--no-save` 不写 .blend。排错时先用 `--dry-run` 看每个部件分到多少面，最省时间。

---

## 5. 配置字段速查（`projects/dragon01/parts.json`）

顶层字段：

| 字段 | 默认 | 含义 |
|---|---|---|
| `source_object` | 自动选面最多 | 源网格对象名。当前 `dragon01_model` |
| `out_dir` | `parts` | 输出目录，相对项目目录 |
| `collection` | `<文件名>_Parts` | Blender 里放部件的集合名 |
| `fill_holes` | `true` | 切完后是否尝试补洞；对非流形切口只能尽力而为 |
| `smoothing_passes` | `3` | 面标签平滑轮数；越大边界越圆滑，也越容易吃掉细部 |
| `min_island_faces` | `30` | 小于这个面数的孤岛丢弃 |
| `island_keep_ratio` | `0.002` | 相对最大岛的比例阈值，和上一项取较大值 |
| `shade_smooth` | `true` | 是否平滑着色 |
| `export_parts_centered` | `true` | 单件 GLB 是否把原点归零 |

每个 `parts[]` 元素：

| 字段 | 必填 | 含义 |
|---|---|---|
| `id` | 是 | 对象名，也是 GLB 文件名；不要重复 |
| `label_zh` | 否 | 验收板上的中文名 |
| `color` | 否 | 视口颜色，`#RRGGBB`；只影响预览 |
| `fallback` | 否 | 兜底部，必须且只能有一个；不能同时写 `seeds`/`capsule` |
| `seeds` | 二选一 | 种子坐标列表，单位米；会自动吸附到最近顶点 |
| `radius_m` | 配 `seeds` 时必填 | 沿表面生长的最远距离，单位米 |
| `capsule` | 二选一 | `{points: [...], radius_m: ...}`，用折线胶囊圈细长部位；优先于种子 |
| `protect` | 否 | 标签平滑时保护该部件，避免边界被邻居吃掉 |
| `fill_holes` | 否 | 覆盖全局补洞开关 |
| `shade_smooth` | 否 | 覆盖全局平滑着色 |
| `solidify_mm` | 否 | 加厚毫米数；`0` 表示不加厚。默认不加厚，原因见第 6 节 |
| `explode_mm` | 否 | 爆炸图位移，单位毫米；只影响预览，不改工程里的实际位置 |

挑种子的小经验：

- 龙头这种块状部位，半径 10–12 cm 比较稳。
- 角、爪这种细部，3–5 cm，并加 `"protect": true`。
- 龙须又细又容易贴身体，别用球，直接用 `capsule` 折线，半径 4–6 mm。
- 种子吸附距离会在日志里打印；超过 2 cm 基本是点错了。

---

## 6. 已知限制（请先看，再决定下一步）

这些不是“没做完”，是这张 AI 网格的客观条件。数字都来自 `parts_manifest.json`。

1. **不是水密实体。** 源网格有 15,740 条非流形边；切开后每个部件仍有一圈开放边。比如龙身 1,340 条边界边、龙头 560 条、龙须 A 119 条。补洞只能补上一部分，不能把分叉的开放链全部封死。
2. **切口是“尽力而为”。** 切割边界沿着非流形连接走，不是干净的闭合环。视觉上接缝对得上，但放大看会有锯齿和缺口。
3. **龙须 A 是 2 个岛。** 1,565 面 + 211 面，两段之间最小间隙约 7.07 mm；源网格本来就可能断开了。它仍是一个对象、一个 GLB，移动时一起动；要彻底接上需要手动桥接。
4. **龙头和鬃毛的边界是近似值。** 种子 + 半径按表面距离生长，没有语义模型。颈部、鬃毛根部可能互相咬掉一点；要更准就调种子/半径，或手动在编辑模式里重新分配。
5. **分件工程本身没有骨骼。** 9 个件是独立对象。项目另有一版**部件级骨架**（见 `projects/dragon01/rig/README.md`）：头、角、鬃毛、3 只爪、2 根龙须能各自动，但身体仍是单根 `body` 骨，不能沿脊柱弯。
6. **没有重新展 UV。** 保留了源 UV `AI3D_Front`；切口附近可能有拉伸，原有的正面投影贴图仍然可用，但不适合做 360° 环拍的新贴图。
7. **GLB 里没有 9 套材质。** 9 个件共用 `Dragon_Bronze`；视口颜色不会自动变成 GLB 材质。要在引擎里分色，需要给每个件单独建材质。
8. **`solidify_mm` 不是万能打印开关。** 我们实测 1.2 mm 加厚会出现边缘毛刺和撕裂感，因为切口本身不干净。它能把一部分开放边变成有厚度的边，但不能保证水密。

如果你要的是“能打印的实体”或“能绑定的角色”，正确顺序不是继续加厚，而是：

- 打印：每个件先 Voxel Remesh（体素重网格）→ 修洞 → Boolean 合并 → 3D Print Toolbox 检查。
- 绑定：每个件手动重拓扑成四边面 → 重新展 UV → 骨架绑定 → 权重绘制。

---

## 7. 下一步能接什么（按推荐顺序）

| 方案 | 做什么 | 成本 | 适合谁 |
|---|---|---|---|
| **Blender 手动清理** | 编辑模式里桥接开放边、合并碎岛、修法线 | 免费，费时间 | 只改几个件 |
| **QuadriFlow（Blender 自带）** | 对单个件重拓扑成四边面 | 免费，可能吃细节 | 要雕刻/绑定 |
| **AutoRemesher / Instant Meshes（外部）** | 批量重拓扑，保留分件结果 | 免费 | 要统一面密度 |
| **P3-SAM / PartField（研究模型）** | 自动语义分件，适合批量换模型 | 需额外环境，效果看模型 | 想把分件做成通用流水线 |
| **Quad Remesher / RetopoFlow（付费）** | 更稳的自动/半自动重拓扑 | 付费 | 量产、商业项目 |

我的建议：

- 你现在这条龙，**先用这份分件工程做局部调整**，不要再整体 remesh。整体重网格化会把刚分好的边界又糊回去。
- 这条龙已经有一版**部件级骨架**：见 `projects/dragon01/rig/README.md`。头、角、鬃毛、3 只爪、2 根龙须能各自动；身体仍是单根 `body` 骨，不能沿脊柱弯。它验证了分件能绑骨，但不是最终动画骨架。重建/验收用 `python3 scripts/blender/run_rig.py --project dragon01`，配置在 `projects/dragon01/rig.json`。
- 如果下一步是“每个件都能独立换材质/做 LOD”，先做**单件 Decimate + 单独材质**，成本最低。
- 如果下一步是“能做身体弯曲的动画”，再上 **QuadriFlow + 手动修边**；这一步无法全自动，别期待一键完成。真正的身体动画要先重拓扑身体、展 UV、加脊柱骨链，光给当前薄壳加骨会拉裂。
- 如果目标是批量处理很多只龙/兽，再考虑 P3-SAM 这类语义分割；单条龙不值得为它搭环境。

---

## 8. 源文件与可重复性

- 源文件：`/home/roland/ai3d/blend/dragon01.blend`，**没有被覆盖**。分件脚本只读它，所有产物写到 `projects/dragon01/parts/`。
- 分件脚本：`/home/roland/ai3d/scripts/blender/25_parts.py`，通用、配置驱动，不绑定龙。
- 预览脚本：`27_parts_preview.py`（Workbench，几秒出图，不占显卡）。
- 验收板：`28_parts_sheet.py`（系统 Python + Pillow）。
- GLB 验收：`29_verify_parts_glb.py`（重新导入并检查网格数、原点、材质）。
- 配置：`projects/dragon01/parts.json`；改完重跑第 4 节即可。
- 每个部件分到多少面、丢了几个小岛、种子吸附到哪，全在 `parts_manifest.json` 里，不用猜。

如果要拿这套流程做新模型：复制 `parts.json` 到新项目目录，改 `source_object` 和种子，然后：

```bash
~/.local/bin/blender -b /path/to/new.blend \
  --python /home/roland/ai3d/scripts/blender/25_parts.py -- \
  --config /home/roland/ai3d/projects/newproject/parts.json
```

先跑 `--print-fps 32` 挑点，再跑 `--dry-run` 看面数，最后正式生成。这样最省时间。
