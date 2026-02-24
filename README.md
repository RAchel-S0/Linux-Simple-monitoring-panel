基于FastAPI，Vue3，Echarts构建的自用linux面板，以补全部分宝塔收费/不方便的功能

内含大量AI成分

包含基本的CPU，内存，网络监控，进程管理，Nginx运行状态，日志分析，docker容器状态，简单的文件管理
监控部分后台静默采集数据，使用SQLite存储

install.sh为安装脚本

chmod +x install.sh
sudo ./install.sh

按1安装，可自定义端口号

如需卸载，再次运行install.sh，按2卸载
默认账号密码admin   admin123
