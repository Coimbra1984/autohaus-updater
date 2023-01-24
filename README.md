# Autohaus updater

This is the update server for the autohaus home automation https://github.com/Coimbra1984/autohaus

# Installation

Installation can be done with pip.
```
pip install autohaus-updater
```

# Start

Once installed, you can start the update server with.
```
python -m autohaus_updater.main --repo_wdir=<PATH TO WORKING DIRECTORY WITH WRITE ACCESS>
```

# Explanation

The autohaus-updater checks out the git sources of the autohaus-server and starts it in a separate process.
The updater opens a rest-api to handle the autohaus updates, which includes the following steps:

- stopping the autohaus server
- updating the git-sources 
- starting the autohaus server again

# Rest API

By default the autohaus-updater listens to an unencrypted rest-api at 127.0.0.1 (localhost) and port 5000.

**You should use it behind a reverse proxy to secure the connection.**

# Command line arguments

The update server is configurable through comamnd line arguments. Run 
```
python3 -m autohaus_updater.main --help
```
to get a list and help of all command line arguments.

# Systemd service

A systemd service file could look like this

```
[Unit]
Description=Autohaus update server
After=multi-user.target

[Service]
Type=notify 
Restart=always
User=pi
ExecStart=/usr/bin/python3 -m autohaus_updater.main --repo_wdir=/home/pi/autohaus --pythonExecutable=/usr/bin/python3 --gitUrl=https://github.com/Coimbra1984/autohaus.git

[Install]
WantedBy=multi-user.target
```

Copy this file to `/etc/systemd/system/autohaus-updater.service`

Update systemd
```
sudo systemctl daemon-reload
```
Enable the service
```
sudo systemctl enable autohaus-updater.service
```
Start the service
```
sudo systemctl start autohaus-updater.service
```

# Nginx reverse proxy

A nginx reverse proxy to force https usage for the domain autohaus.mydomain.com could look like the following. It implements basic authentication with auth_basic.
Note that it also redirects any `/autohaus` calls to port 5001 which is the actual autohaus-server started by the autohaus-updater.

This means that any calls to 

- https://autohaus.mydomain.com/autohaus/ ... are redirected to 127.0.0.1:5001
- https://autohaus.mydomain.com/autohaus-update/ ... are redirected to 127.0.0.1:5000

**WARNING: use at your own risc, no guarantee!**

```
server {
  listen 80;
  listen [::]:80;
  server_name autohaus.mydomain.com;

  return 301 https://$host$request_uri;

  location ^~ /.well-known/acme-challenge/ {
    proxy_pass http://localhost:60000;
  }
}

server {
  listen 443 ssl;
  server_name autohaus.mydomain.com;

  location /autohaus-update {
      proxy_buffering                         off;
      proxy_set_header Host                   $http_host;
      proxy_set_header X-Real-IP              $remote_addr;
      proxy_set_header X-Forwarded-For        $proxy_add_x_forwarded_for;
      proxy_set_header X-Forwarded-Proto      $scheme;
      proxy_pass         "http://127.0.0.1:5000";
      auth_basic           "autohaus-update server administrator's area";
      auth_basic_user_file /etc/nginx/.htpasswd;
  }
  
  location /autohaus {
      proxy_buffering                         off;
      proxy_set_header Host                   $http_host;
      proxy_set_header X-Real-IP              $remote_addr;
      proxy_set_header X-Forwarded-For        $proxy_add_x_forwarded_for;
      proxy_set_header X-Forwarded-Proto      $scheme;
      proxy_pass         "http://127.0.0.1:5001";
      auth_basic           "autohaus server administrator's area";
      auth_basic_user_file /etc/nginx/.htpasswd;
  }

  ssl_certificate /etc/letsencrypt/live/autohaus.mydomain.com/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/autohaus.mydomain.com/privkey.pem;

  ssl_protocols TLSv1.2 TLSv1.3;
  ssl_prefer_server_ciphers on;
  ssl_ciphers 'kEECDH+ECDSA+AES128 kEECDH+ECDSA+AES256 kEECDH+AES128 kEECDH+AES256 kEDH+AES128 kEDH+AES256 DES-CBC3-SHA +SHA !aNULL !eNULL !LOW !kECDH !DSS !MD5 !RC4 !EXP !PSK !SRP !CAMELLIA !SEED';

  add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
  add_header 'Access-Control-Allow-Origin' "$http_origin" always;
  add_header 'Access-Control-Allow-Credentials' 'true' always;
  add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
  add_header 'Access-Control-Allow-Headers' 'Accept,Authorization,Cache-Control,Content-Type,DNT,If-Modified-Since,Keep-Alive,Origin,User-Agent,X-Requested-With' always;

  access_log /var/log/nginx/packages-error.log;
  error_log /var/log/nginx/packages-error.log;

  root /var/www/html;
}

```
