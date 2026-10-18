# 原生构建：vcpkg 与 xmake

依赖由 `vcpkg.json` 的 builtin baseline 固定；xmake 只构建本项目，不再用临时 `g++` 命令直接编译，也不从 xmake-repo 解析第三方包。Highway 1.4.0 用于矩形批量碰撞；pdqsort 2019-07-30#2 用于带原始索引最终裁决的搜索排名排序。稳定排序和没有全序裁决的排序保持原实现。

## Linux

安装 C++17 编译器、xmake（2.9+）、vcpkg；vcpkg 构建依赖还需要 CMake、Ninja、pkg-config 等基础工具。然后在项目根目录执行：

```sh
python -m pip install -r requirements-native.txt
vcpkg install --triplet x64-linux
python -m tools.build_native --install
python -m pip install -r requirements-accelerated.txt
python -m tools.build_accelerators --native
```

`tools.build_native` 在独立临时目录调用 `xmake f` 和 `xmake`，避免多个进程争用项目配置；安装代码镜像及对应身份清单。默认按本机 CPU 编译。需要可分发的基础指令集镜像时，在构建和运行时均设置 `NOHIT_NATIVE_TUNE=portable`。Highway 使用当前编译目标的静态 SIMD 分发，没有运行时新增动态库依赖。

直接使用 xmake 也可以构建，但 Python 安装助手还负责生成运行时验证清单：

```sh
xmake f -m release --host_tune=y --vcpkg_triplet=x64-linux
xmake native_frontier
python -m tools.build_native --install
```

自定义位置：

```sh
vcpkg install --triplet x64-linux --x-install-root=build/vcpkg_installed
python -m tools.build_native --install --vcpkg-installed build/vcpkg_installed
# 源码运行时发生重编译也要使用这个安装根目录：
export NOHIT_VCPKG_INSTALLED="$PWD/build/vcpkg_installed"
```

`XMAKE` 可以指定 xmake 可执行文件。`CXX` 可以选择编译器，构建器将其传入 xmake 的配置。已安装镜像只依赖编译器运行库；其源码、附加头文件、xmake 配置、vcpkg manifest、CPU 身份和二进制哈希均参与一致性检查。修改构建输入会使旧镜像失效。

## 对照版本

```sh
# 不使用第三方库，仍然通过 xmake 构建。
python -m tools.build_native --highway off --pdqsort off --output build/scalar.so

# 两个候选可以分别关闭。
python -m tools.build_native --highway on --pdqsort off --output build/highway.so
python -m tools.build_native --highway off --pdqsort on --output build/pdqsort.so
```

环境变量 `NOHIT_NATIVE_SIMD=off|highway|auto` 和 `NOHIT_NATIVE_SORT=std|pdqsort|auto` 可以强制选择匹配版本；`auto` 接受已安装版本，未安装时构建含两个库的版本。切换版本会使用不同的代码缓存，完全不复用路线或弹幕世界。基准前应先在相同变量下调用 `load_backend()`，将编译和解算耗时分开。

```sh
python -m tools.benchmark_native_libraries --scalar build/scalar.so --highway build/highway.so --out build/collision-comparison.json
python -m tools.benchmark_library_variants --csv attack.csv --entry entry.json --out build/library-comparison
```

局部碰撞吞吐不代表完整解算收益。完整求解可能因预算内的搜索分支竞争而选择不同路线，必须同时报告成功次数、独立验证和完整耗时；unknown 不算加速成功。四边形轴投影曾尝试 Highway，但局部测量更慢，已保留标量实现。

## Windows 与 macOS

`tools.build_native --triplet ...` 按主机选择 x64/arm64，默认 Windows 为 `x64-windows-static`，macOS 为对应的 `*-osx`。手动 xmake 配置时明确指定 `--vcpkg_triplet`。Windows 的 DLL 接口通过 xmake 导出规则生成；使用 MSVC 时采用 `/fp:strict`。当前性能和原游戏回放证据仅在 Linux x86_64 上测得，其他平台需要各自运行行为一致性测试。

依赖的许可证保存在 `vcpkg_installed/<triplet>/share/<port>/copyright`；发布头文件或二进制时应同时携带对应许可证。
