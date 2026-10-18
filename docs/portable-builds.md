# Windows / Linux 自动构建

每次 push（所有分支）、pull request 和手动运行都会执行
[Portable Windows and Linux](https://github.com/Tartarus-Game/nohit/actions/workflows/build.yml)。
两个平台独立构建，不构建 macOS，也不会取消较早提交的构建。

在成功的运行页面底部下载对应 Artifact，解开 GitHub 外层压缩包后，再解开平台包：

| 平台 | 平台包 | 启动方式 |
| --- | --- | --- |
| Windows 10/11 x64 | `nohit-windows-x64.zip` | 双击 `nohit.exe` |
| Linux x86_64，glibc ≥ 2.35 | `nohit-linux-x64.tar.xz` | `tar -xf nohit-linux-x64.tar.xz`，然后 `./nohit/nohit` |

浏览器打开 `http://127.0.0.1:8080`。可通过 `nohit 8081` 指定其他端口。
请完整解压到可写目录，并保留可执行文件旁的 `_internal` 文件夹。
用户设备不需要安装 Python、C++ 编译器、xmake、vcpkg 或下载依赖。

## 构建和验收

- vcpkg 使用 `vcpkg.json` 的固定 baseline；xmake 3.1.2 编译 C++17 内核。
- CI 使用 Python 3.12，提前编译四个独立标量验证模块，冻结所需 Python/NumPy 运行时。
- 分发使用 portable CPU 目标，不使用构建机器的 `-march=native`。
- Windows C++ 内核静态链接 MSVC 运行库；Python/NumPy 所需 DLL 由打包工具收集。
- 包含 Dashboard、完整 `c2-sans-fight` 资源、原始语义源文件和依赖许可证。
  不包含历史验证记录、测试集、开发工具链、Numba/LLVM、未使用的 NumPy FFT/随机模块。
- 先运行操作目标/失败诊断/难度分析测试，再解压最终平台包进行真实解算、独立验证和服务初始化自测。
  自测禁止发现编译器和启动子进程；冻结版本缺失或校验不通过的内核会直接报错。
- 每个平台压缩包必须 ≤ **20,000,000 字节**，超限会使构建失败，不会显示为成功发布。
  Linux 使用 xz 并保留共享库链接，Windows 使用标准 ZIP。
- Artifact 同时提供 SHA-256 和实际字节数报告，保留 30 天。GitHub 外层包装与解压后体积不计入平台包预算。

本地复现（仅开发者需要工具链）：安装 `requirements-build.txt`，执行 vcpkg install，
设置 `NOHIT_NATIVE_TUNE=portable`，依次运行 `python -m tools.build_native --install`、
`python -m tools.build_accelerators`、`python -m tools.package_portable`。
输出位于 `build/releases/`。Linux CI 固定 Ubuntu 22.04；在更高版本 glibc 上自行构建的包
不承诺兼容更旧系统，包内 `START.txt` 会记录本次构建的 glibc 基线。
