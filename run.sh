cat > ~/teleprompter/run.sh <<'EOF'
#!/bin/bash
cd /home/admin/teleprompter
source venv/bin/activate
python teleprompter.py
EOF
