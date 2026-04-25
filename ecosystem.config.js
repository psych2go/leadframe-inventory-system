module.exports = {
  apps: [{
    name: 'leadframe-inv',
    cwd: '/opt/leadframe-inventory/backend',
    interpreter: '/opt/leadframe-inventory/backend/venv/bin/python',
    script: '/opt/leadframe-inventory/backend/venv/bin/uvicorn',
    args: 'main:app --host 127.0.0.1 --port 8000',
    env_file: '/opt/leadframe-inventory/.env',
    max_memory_restart: '500M',
    log_date_format: 'YYYY-MM-DD HH:mm:ss',
    error_file: '/opt/leadframe-inventory/logs/pm2-error.log',
    out_file: '/opt/leadframe-inventory/logs/pm2-out.log',
  }]
}
