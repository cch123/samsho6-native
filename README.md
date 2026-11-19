# 侍魂 6 原生重构

用 C++20 和 SDL3 还原日版 PS2《侍魂 6》的本地双人对战。角色进度、操作和验证范围见 [试玩说明](README.txt)，后续工作见 [开发计划](docs/development-plan.txt)。

## 构建

在已安装 CMake、C++20 编译器和 SDL3 的环境中，从项目根目录执行：

```sh
cmake -S . -B work/ss6/build-native -DCMAKE_BUILD_TYPE=Release
cmake --build work/ss6/build-native -j 4
```

运行游戏需要从自己的日版光盘镜像准备资源。资源提取和验证脚本位于 [work/ss6](work/ss6)。已有本地资源目录 `work/ss6/extracted/resources/` 时，可在 macOS 上打包并启动选人：

```sh
mkdir -p outputs/ss6-feasibility/native-viewer/assets
python3 work/ss6/package_viewer.py
./select.command
```

双击 `cpu.command` 可用 1P 直接对战电脑。要自行选人，可运行 `./select.command --cpu p2`。

双击项目根目录的 `title.command` 可从日版标题进入本地双人 VS。赛后选择 `RETURN TO TITLE` 可以从模式菜单重开一场。

Git 只跟踪源码、脚本、开发文档和对战测试输入。光盘镜像、原版可执行文件、提取出的图像与音频、截图、录像以及打包产物均保留在本地。
