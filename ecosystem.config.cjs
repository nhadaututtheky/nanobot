module.exports = {
  apps: [
    {
      name: "nanobot",
      script: "python",
      args: "-m nanobot gateway",
      cwd: "D:/Project/NanoBot",
      interpreter: "none",
      autorestart: true,
      max_restarts: 10,
      restart_delay: 5000,
      watch: false,
      env: {
        PYTHONIOENCODING: "utf-8",
        PYTHONUNBUFFERED: "1",
      },
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      error_file: "C:/Users/X/.nanobot/logs/error.log",
      out_file: "C:/Users/X/.nanobot/logs/out.log",
      merge_logs: true,
      max_size: "10M",
      retain: 3,
    },
  ],
};
