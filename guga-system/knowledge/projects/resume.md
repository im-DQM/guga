# 简历（孟庆达 · 后端开发 C++）

2026-10-25 建。主人的简历原件与 LaTeX 正式版都放在一起，别散落。

## 文件

| 内容 | 路径 |
| --- | --- |
| 原件（Word，主人自己维护的版本） | `~/docs/personal/resume/简历-孟庆达-2026-10-25.docx` |
| LaTeX 正式版 PDF（一页 A4，字体已嵌入，文字可提取） | `~/docs/personal/resume/孟庆达-简历-LaTeX版-2026-10-25.pdf` |
| 预览图（130 dpi PNG） | `~/docs/personal/resume/预览-2026-10-25.png` |
| LaTeX 源码工程 | `~/docs/personal/resume/latex/mengqingda-resume.tex` + `resume.cls` |

## 怎么重新出 PDF

```bash
cd ~/docs/personal/resume/latex
xelatex -interaction=nonstopmode mengqingda-resume.tex   # 跑两遍更稳
cp mengqingda-resume.pdf ../孟庆达-简历-LaTeX版-$(date +%F).pdf
pdftoppm -r 130 -png mengqingda-resume.pdf preview       # 预览图
```

## 模板与字体（踩过的坑）

- 模板：`billryan/resume` 的 `zh_CN` 分支（CC BY 4.0），单栏、纯文字、ATS 友好。原版依赖 `fonts/Main/` 内部字体与 fontawesome（texlive-fonts-extra 太大），已改写 `resume.cls`：西文 TeX Gyre Termes，中文 Fandol，节标题不加图标。
- **中文字体不能用系统的 Noto CJK ttc**：`\setCJKmainfont{Noto Serif CJK SC}` 会落到日文字形（pdffonts 里显示 `NotoSerifCJKjp`）。用 texlive 自带的 Fandol，必须带 `Path=...` + `Extension=.otf` + `UprightFont/BoldFont`，否则 fontspec 找不到。
- 服务器依赖：`texlive-xetex texlive-latex-recommended texlive-latex-extra texlive-lang-chinese fonts-noto-cjk poppler-utils`（2026-10-25 已装）。
- GitHub 直连拉仓库会超时（git clone / codeload 都慢），**改走 `https://fastly.jsdelivr.net/gh/<owner>/<repo>@<branch>/<file>`** 单文件取，秒回。

## 内容待补（等主人给真数）

1. 高并发内存池：分配/释放吞吐相对 malloc 提升多少、多线程场景下的锁竞争下降比例。
2. LLaMA 推理内核：CPU 与 GPU 各自的 tokens/s、首 token 延迟、Q4_0 相对 F32 的加速比。
3. 是否补「获奖情况」「其他（GitHub / 博客）」两节——现在留空，没有就不硬凑。

## 主人偏好

- 观感选国内技术简历常见的一页纸（billryan 那种），不要花哨多栏、不要技能进度条（AI 筛选读不了）。
- Word 原件保留，给需要 .docx 的网申系统用；PDF 用于投递与内推。
