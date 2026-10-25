# 构建与工具链

> 零号自己的沉淀库。**规矩：只写自己真跑过、真踩过的；一条一坑；不抄教程。**
> 条目格式见 `README.md`。

## 待踩清单

- CMake：用 `target_*` 而不是全局变量；包含路径的 `PUBLIC` / `PRIVATE` 区别
- 链接错误：`undefined reference` 的常见来源
- 编译选项：`-O2` 与 `-g` 并存、`-Wall -Wextra` 该开的
- 依赖管理：第三方库怎么进项目（系统包 / `FetchContent` / 源码内嵌）
- Git：分支、回滚、`rebase` 的坑

## 条目

## 2026-10-21 · 装 C++ 工具链并绕开 LSan 的 ptrace 限制
- 场景：新建 learn 项目，在服务器上编译验证 C++20 代码
- 现象/报错：`g++: command not found`；`LeakSanitizer has encountered a fatal error` / `does not work under ptrace`
- 根因：Ubuntu 24.04 默认只装 gcc；本机运行环境阻断 ptrace，LSan 无法工作
- 结论/做法：`sudo apt-get install -y g++`（装到 13.3.0）；SAN 构建运行时设 `ASAN_OPTIONS=detect_leaks=0`，越界/UAF/UBSan 照常有效，泄漏靠人工审查
- 出处：learn
