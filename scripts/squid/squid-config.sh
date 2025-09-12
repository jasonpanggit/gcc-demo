#!/bin/bash

# Squid Proxy Configuration Script
# This script installs and configures Squid proxy server on Ubuntu

# Update package list
apt-get update

# Install Squid proxy server
apt-get install -y squid openssl

# Create SSL certificate directory
mkdir -p /etc/squid/ssl_cert
chown proxy:proxy /etc/squid/ssl_cert
chmod 700 /etc/squid/ssl_cert

# Generate self-signed certificate for SSL bump
openssl req -new -newkey rsa:2048 -sha256 -days 365 -nodes -x509 \
    -extensions v3_ca \
    -keyout /etc/squid/ssl_cert/squid-ca-key.pem \
    -out /etc/squid/ssl_cert/squid-ca-cert.pem \
    -subj "/C=AU/ST=NSW/L=Sydney/O=Azure Hub/OU=IT Department/CN=Squid Proxy CA"

# Set proper permissions for SSL certificates
chown proxy:proxy /etc/squid/ssl_cert/squid-ca-*.pem
chmod 600 /etc/squid/ssl_cert/squid-ca-*.pem

# Create SSL database directory
mkdir -p /var/lib/squid/ssl_db
chown proxy:proxy /var/lib/squid/ssl_db
chmod 700 /var/lib/squid/ssl_db

# Initialize SSL certificate database
/usr/lib/squid/security_file_certgen -c -s /var/lib/squid/ssl_db -M 4MB
chown -R proxy:proxy /var/lib/squid/ssl_db

# Backup original configuration
cp /etc/squid/squid.conf /etc/squid/squid.conf.backup

# Create new Squid configuration
cat > /etc/squid/squid.conf << 'EOF'
# Squid Configuration for Azure Hub VNet with SSL Bump
# HTTP proxy port
http_port 3128

# HTTPS intercept port with SSL bump
https_port 3129 intercept ssl-bump \
    cert=/etc/squid/ssl_cert/squid-ca-cert.pem \
    key=/etc/squid/ssl_cert/squid-ca-key.pem \
    generate-host-certificates=on \
    dynamic_cert_mem_cache_size=4MB

# SSL bump configuration
ssl_bump_dir /var/lib/squid/ssl_db

# SSL bump rules
acl step1 at_step SslBump1
acl step2 at_step SslBump2
acl step3 at_step SslBump3

# Don't bump these sites (banking, government, etc.)
acl nobump_sites ssl::server_name "/etc/squid/nobump_sites.txt"

# SSL bump decisions
ssl_bump peek step1
ssl_bump splice nobump_sites
ssl_bump bump all

# Access Control Lists (ACLs)
acl localnet src 172.16.0.0/16     # Hub VNet
acl localnet src 10.0.0.0/16       # Gen VNet
acl localnet src 100.0.0.0/16      # Non-Gen VNet
acl localnet src 192.168.0.0/16    # On-premises networks

acl SSL_ports port 443
acl Safe_ports port 80              # http
acl Safe_ports port 21              # ftp
acl Safe_ports port 443             # https
acl Safe_ports port 70              # gopher
acl Safe_ports port 210             # wais
acl Safe_ports port 1025-65535      # unregistered ports
acl Safe_ports port 280             # http-mgmt
acl Safe_ports port 488             # gss-http
acl Safe_ports port 591             # filemaker
acl Safe_ports port 777             # multiling http
acl CONNECT method CONNECT

# Recommended minimum Access Permission configuration:
# Deny requests to certain unsafe ports
http_access deny !Safe_ports

# Deny CONNECT to other than secure SSL ports
http_access deny CONNECT !SSL_ports

# Only allow cachemgr access from localhost
http_access allow localhost manager
http_access deny manager

# Allow access from local networks
http_access allow localnet
http_access allow localhost

# And finally deny all other access to this proxy
http_access deny all

# Uncomment and adjust the following to add a disk cache directory.
cache_dir ufs /var/spool/squid 100 16 256

# Leave coredumps in the first cache dir
coredump_dir /var/spool/squid

# Add any of your own refresh_pattern entries above these.
refresh_pattern ^ftp:           1440    20%     10080
refresh_pattern ^gopher:        1440    0%      1440
refresh_pattern -i (/cgi-bin/|\?) 0     0%      0
refresh_pattern .               0       20%     4320

# Logging
access_log /var/log/squid/access.log squid
cache_log /var/log/squid/cache.log

# DNS settings
dns_nameservers 168.63.129.16

# Performance tuning
maximum_object_size 4096 KB
minimum_object_size 0 KB
cache_mem 256 MB

# Headers
forwarded_for on
via on

# SSL bump helpers
sslcrtd_program /usr/lib/squid/security_file_certgen -s /var/lib/squid/ssl_db -M 4MB
sslcrtd_children 8 startup=1 idle=1

# Error pages
error_directory /usr/share/squid/errors/English

# SSL bump error page
sslproxy_cert_error allow all
EOF

# Set proper permissions
chown proxy:proxy /etc/squid/squid.conf
chmod 644 /etc/squid/squid.conf

# Create nobump sites list (sites that should not be SSL bumped)
cat > /etc/squid/nobump_sites.txt << 'EOF'
# Banking and financial sites
.bankofamerica.com
.chase.com
.wellsfargo.com
.citibank.com
.paypal.com
.visa.com
.mastercard.com

# Government sites
.gov
.mil

# Cloud provider authentication
login.microsoftonline.com
.azure.com
accounts.google.com
aws.amazon.com

# Certificate authorities
.digicert.com
.verisign.com
.symantec.com

# Add your own sites here that should not be SSL bumped
EOF

chown proxy:proxy /etc/squid/nobump_sites.txt
chmod 644 /etc/squid/nobump_sites.txt

# Create cache directories
squid -z

# Enable and start Squid service
systemctl enable squid
systemctl start squid

# Configure firewall (ufw)
ufw allow 3128/tcp  # HTTP proxy port
ufw allow 3129/tcp  # HTTPS intercept port
ufw allow 22/tcp    # SSH
ufw --force enable

# Create a simple status check script
cat > /home/${squid_admin_username}/check_squid.sh << 'EOF'
#!/bin/bash
echo "=== Squid Proxy Status ==="
systemctl status squid

echo ""
echo "=== Squid Access Log (last 20 lines) ==="
tail -20 /var/log/squid/access.log

echo ""
echo "=== Squid Cache Log (last 10 lines) ==="
tail -10 /var/log/squid/cache.log

echo ""
echo "=== Squid Configuration Test ==="
squid -k parse

echo ""
echo "=== SSL Certificate Database Status ==="
ls -la /var/lib/squid/ssl_db/

echo ""
echo "=== SSL Certificate Information ==="
openssl x509 -in /etc/squid/ssl_cert/squid-ca-cert.pem -text -noout | head -20

echo ""
echo "=== Network Configuration ==="
ip addr show

echo ""
echo "=== Open Ports ==="
ss -tlnp | grep -E ":(3128|3129|22)"
EOF

chmod +x /home/${squid_admin_username}/check_squid.sh
chown ${squid_admin_username}:${squid_admin_username} /home/${squid_admin_username}/check_squid.sh

# Create CA certificate export script
cat > /home/${squid_admin_username}/export_ca_cert.sh << 'EOF'
#!/bin/bash
echo "=== Squid Proxy CA Certificate Export ==="
echo "CA certificate location: /etc/squid/ssl_cert/squid-ca-cert.pem"
echo ""
echo "To use SSL bump, clients must trust this CA certificate."
echo ""
echo "=== Certificate in PEM format ==="
cat /etc/squid/ssl_cert/squid-ca-cert.pem
echo ""
echo "=== Certificate in DER format (for Windows) ==="
openssl x509 -in /etc/squid/ssl_cert/squid-ca-cert.pem -outform DER -out /tmp/squid-ca-cert.der
echo "DER certificate saved to: /tmp/squid-ca-cert.der"
echo ""
echo "=== Certificate Information ==="
openssl x509 -in /etc/squid/ssl_cert/squid-ca-cert.pem -text -noout
echo ""
echo "=== Installation Instructions ==="
echo "1. Copy the certificate to client machines"
echo "2. Windows: Import into 'Trusted Root Certification Authorities'"
echo "3. Linux: Copy to /usr/local/share/ca-certificates/ and run update-ca-certificates"
echo "4. macOS: Add to Keychain and mark as trusted"
echo "5. Configure browser/application to use proxy: <squid-ip>:3128"
EOF

chmod +x /home/${squid_admin_username}/export_ca_cert.sh
chown ${squid_admin_username}:${squid_admin_username} /home/${squid_admin_username}/export_ca_cert.sh

# Create log rotation for Squid logs
cat > /etc/logrotate.d/squid << 'EOF'
/var/log/squid/*.log {
    daily
    compress
    delaycompress
    rotate 7
    missingok
    notifempty
    sharedscripts
    postrotate
        /usr/bin/systemctl reload squid
    endscript
}
EOF

# Ensure Squid starts on boot
systemctl enable squid

echo "Squid Proxy with SSL Bump installation and configuration completed successfully!"
echo "HTTP Proxy is available on port 3128"
echo "HTTPS Intercept is available on port 3129"
echo "Use /home/${squid_admin_username}/check_squid.sh to check proxy status"
echo "Use /home/${squid_admin_username}/export_ca_cert.sh to export CA certificate for client installation"
echo ""
echo "IMPORTANT: For SSL bump to work, clients must trust the CA certificate!"
echo "CA certificate location: /etc/squid/ssl_cert/squid-ca-cert.pem"
