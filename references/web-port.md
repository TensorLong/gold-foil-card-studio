# 只有用户需要网页时才迁移

优先复用已有 Three.js 或原生查看器；不要为只要 Blender 工程的用户另建 Web 项目。导出几何的 GLB 不携带自定义节点，必须实现新的金卡材质。

原生 WebGL 可复制 [../assets/renderer.js](../assets/renderer.js) 与 MIT `LICENSE`，使用 `createCardRenderer(canvas, config)`，调用 `draw(rotateXDegrees, rotateYDegrees, emission, repeat, perspectivePixels/cardWidthPixels)`，销毁时 `dispose()`。此实现用于本技能的全金 demo；不要再从彩虹 shader 改颜色。

画布包含宽度 10% 的透明留边，卡面元素须 `overflow:visible`，canvas 定位 `left:-10%; top:calc(-10% / var(--aspect)); width:120%; height:calc(100% + 20% / var(--aspect))`，`--aspect` 是纹理高/宽；卡面布局自身仍使用原始宽高比。背面不要复用正面图案。若宿主已有渲染器则迁移下面的数学与留边语义，无需引入第二个引擎。

透明输出使用预乘 alpha：WebGL 设置 `premultipliedAlpha:true`，最终输出 `vec4(premultipliedRGB, alpha)`，不要再除以 alpha。iOS 透明 WKWebView 的合成曾把低透明度的非预乘辉光显示为饱和黄红硬边。检查默认帧缓冲的每通道 RGB 不超过 alpha（8 位量化容差 1），并确认卡外仍有柔和半透明像素；不能以裁掉辉光作为修复。中间 RGBM 缓冲保留自己的 HDR 编码，不是透明合成输出。

保持同一坐标系：对于世界空间表面法向 `N` 和从表面指向观察者的 `V`，反射方向是 `reflect(-V, N)`。若改用卡片局部空间，N、V 和映射旋转必须一起变换，不能混用 glTF 转轴后的网格与根节点坐标。

```glsl
// r = MappingRotation * reflect(-V, N), normalized N and V.
float q = (r.x + r.y + r.z) / 3.0;
q = (q + noiseAmount * noiseValue + phase) * repeatCount;
float triangle = 1.0 - abs(mod(q, 2.0) - 1.0);
float sweep = clamp((triangle - sweepBlack) / (sweepWhite - sweepBlack), 0.0, 1.0);
float line = 1.0 - clamp((lineValue - lineBlack) / (lineWhite - lineBlack), 0.0, 1.0);
float mask = sweep * line;
// Linear-space composition; bloom and tone mapping happen afterwards.
vec3 color = mix(printedColor, goldColor * emissionStrength, mask);
```

噪波、印刷光照与 AgX 实现不同会造成渲染差异；近似版应明确说明，不能宣称和 Blender 像素一致。`lineart` 以数据纹理读取，`artwork` 做 sRGB→线性转换。不可用彩虹正弦、仅随时间滚动的渐变、整卡 CSS 滤镜替代这个契约。

共同黑白母版模式不对母版做 sRGB 转换：`printedColor = mix(printPalette.ink, printPalette.stock, master.r)`，两色本身是线性 RGB。彩色素材模式保持上面的 sRGB 解码。两种模式都复用相同线稿、反射与扫光通路。

全金效果应在背景花纹、边框、文字和主体同时有可用线稿，且它们在角度扫描中分别出现可见反光。加入这四类区域的发光开/关差异检查；不得只检查整帧平均像素差。以同一姿态拍发光关/开与正面/左倾/右倾截图，目视对照视频，自动 PASS 只代表通路正常。

视频末段有向卡外扩散的 Fog Glow。网页辉光缓冲需要透明留边，发光源仍按卡片轮廓裁切；不能用 `overflow:hidden` 把所有辉光截在卡内。透视观察位置应与 CSS3D 的 perspective 对齐。卡背可独立设计，但不能把正面镜像当背面。

在真实浏览器验收：纹理加载和 shader 编译无错误；拖动两个方向可见不同位置的金线；修改发光强度与重复数有可观察效果；翻面不把正面镜像当背面；手机宽度无溢出；重置、键盘及减弱动态效果可用。用户未要求发布时只用本机回环地址，不自行部署或公开上传。
