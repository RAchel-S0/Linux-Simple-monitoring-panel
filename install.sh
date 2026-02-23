#!/bin/bash

# ==============================================================================
# Linux Server Monitor Web Panel - One-Click Installer & Uninstaller
# ==============================================================================

GREEN='\033[1;32m'
RED='\033[1;31m'
NC='\033[0m' # No Color

INSTALL_DIR="/opt/linux-server-monitor"
SERVICE_NAME="linux-monitor"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
PORT=8000

# Require root privileges
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}Error: This script must be run as root (sudo).${NC}"
  exit 1
fi

function show_menu() {
    echo -e "\n${GREEN}=== Linux Server Monitor Manager ===${NC}"
    echo "1) Install & Start Monitor Panel"
    echo "2) Uninstall & Remove entirely"
    echo "3) Restart Monitor Service"
    echo "4) Show Status"
    echo "5) Update Panel Code"
    echo "0) Exit"
    echo -e "====================================\n"
}

function install_panel() {
    echo -e "${GREEN}[*] Starting Installation...${NC}"

    read -p "Enter listening port for the Web Panel [Default 8000]: " USER_PORT
    PORT=${USER_PORT:-8000}
    echo -e "${GREEN}[*] Web panel will run on port ${PORT}...${NC}"
    
    # 1. Check prerequisites
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}[!] python3 is not installed. Attempting to install...${NC}"
        if command -v apt-get &> /dev/null; then
            apt-get update && apt-get install -y python3 python3-venv python3-pip
        elif command -v yum &> /dev/null; then
            yum install -y python3 python3-pip
        else
            echo -e "${RED}Failed to automatically install python3. Please install it manually.${NC}"
            exit 1
        fi
    fi

    # 2. Setup directory
    if [ ! -d "$INSTALL_DIR" ]; then
        echo -e "${GREEN}[*] Creating installation directory ${INSTALL_DIR}...${NC}"
        mkdir -p "$INSTALL_DIR"
    else
        echo -e "${GREEN}[*] ${INSTALL_DIR} already exists. Updating contents...${NC}"
    fi
    
    # Use rsync to avoid copying local venv, __pycache__, or temporary databases into the production dir
    echo -e "${GREEN}[*] Copying core application files to ${INSTALL_DIR}...${NC}"
    rsync -av --exclude='venv' --exclude='__pycache__' --exclude='*.db' --exclude='data' ./* "$INSTALL_DIR/"

    # 3. Setup Virtual Environment and Dependencies
    echo -e "${GREEN}[*] Setting up Python virtual environment...${NC}"
    cd "$INSTALL_DIR" || exit
    
    if command -v apt-get &> /dev/null && ! dpkg -l | grep -q "python3-venv"; then
        apt-get install -y python3-venv
    fi

    python3 -m venv venv
    
    echo -e "${GREEN}[*] Installing dependencies from requirements.txt...${NC}"
    source venv/bin/activate
    pip install setuptools wheel
    pip install -r requirements.txt
    deactivate

    # 4. Create Systemd Service
    echo -e "${GREEN}[*] Creating systemd service file...${NC}"
    cat <<EOF > "$SERVICE_FILE"
[Unit]
Description=Linux Server Monitor Web Panel
After=network.target

[Service]
User=root
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/uvicorn main:app --host 0.0.0.0 --port $PORT
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

    # 5. Start and Enable Service
    echo -e "${GREEN}[*] Enabling and starting the service...${NC}"
    systemctl daemon-reload
    systemctl enable $SERVICE_NAME
    systemctl start $SERVICE_NAME

    # Check status
    if systemctl is-active --quiet $SERVICE_NAME; then
        echo -e "\n${GREEN}====================================================${NC}"
        echo -e "${GREEN}SUCCESS: The monitor panel is now running!${NC}"
        echo -e "Access it via: http://<your_server_ip>:$PORT"
        echo -e "Default Login: admin / admin123"
        echo -e "${GREEN}====================================================${NC}"
    else
        echo -e "\n${RED}Service failed to start. You can check logs with: journalctl -u $SERVICE_NAME -f${NC}"
    fi
}

function uninstall_panel() {
    echo -ne "${RED}Are you sure you want to completely remove the panel? (y/N): ${NC}"
    read -r confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        echo "Uninstallation cancelled."
        return
    fi
    
    echo -e "${GREEN}[*] Stopping and disabling service...${NC}"
    systemctl stop $SERVICE_NAME 2>/dev/null
    systemctl disable $SERVICE_NAME 2>/dev/null
    
    echo -e "${GREEN}[*] Removing systemd service file...${NC}"
    rm -f "$SERVICE_FILE"
    systemctl daemon-reload
    
    echo -e "${GREEN}[*] Removing installation directory...${NC}"
    rm -rf "$INSTALL_DIR"
    
    echo -e "${GREEN}SUCCESS: Complete uninstallation is done.${NC}"
}

function manage_service() {
    action=$1
    echo -e "${GREEN}[*] Executing: systemctl $action $SERVICE_NAME...${NC}"
    systemctl "$action" $SERVICE_NAME
    if [ "$action" == "status" ]; then
        return
    fi
    echo -e "${GREEN}Done.${NC}"
}

function update_panel() {
    echo -e "${GREEN}[*] Updating Linux Server Monitor Code...${NC}"
    if [ ! -d "$INSTALL_DIR" ]; then
        echo -e "${RED}[!] The panel is not installed at $INSTALL_DIR. Please install it first.${NC}"
        return
    fi
    
    echo -e "${GREEN}[*] Copying new files to $INSTALL_DIR...${NC}"
    # Copy files excluding python virtual env or db files that may exist in run env
    rsync -av --exclude='venv' --exclude='data' --exclude='*.db' ./* "$INSTALL_DIR/"
    
    echo -e "${GREEN}[*] Restarting service to apply changes...${NC}"
    systemctl restart $SERVICE_NAME
    echo -e "${GREEN}SUCCESS: Panel updated and restarted.${NC}"
}

# Run
while true; do
    show_menu
    read -p "Choose an option [0-5]: " choice
    case $choice in
        1) install_panel ;;
        2) uninstall_panel ;;
        3) manage_service "restart" ;;
        4) manage_service "status" ;;
        5) update_panel ;;
        0) exit 0 ;;
        *) echo -e "${RED}Invalid option.${NC}" ;;
    esac
done
