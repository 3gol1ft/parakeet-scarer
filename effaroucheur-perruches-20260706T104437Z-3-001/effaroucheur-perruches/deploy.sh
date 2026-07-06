#!/bin/bash
# A lancer sur la carte apres chaque upload depuis Windows :
#   bash ~/effaroucheur-perruches/deploy.sh

BASE=~/effaroucheur-perruches/unoq

chmod +x "$BASE/.venv/bin/python"
chmod +x "$BASE/.venv/bin/python3"
chmod +x "$BASE/models/perruche.eim"

sudo systemctl restart effaroucheur
sleep 2
sudo systemctl status effaroucheur --no-pager -l

IP=$(hostname -I | awk '{print $1}')
echo ""
echo "Dashboard : http://${IP}:5000"
