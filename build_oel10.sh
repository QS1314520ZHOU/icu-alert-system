cd /opt
tar xzf icu-alert-system-cpu-1.0.0.el10.x86_64.tar.gz
cd icu-alert-system-cpu
vi .env          # 配 MongoDB host、Redis、LLM_BASE_URL 等
./install.sh     # 装成 systemd 服务
systemctl start icu-alert
systemctl status icu-alert
