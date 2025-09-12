#!/bin/bash

# Update system
apt-get update -y
apt-get upgrade -y

# Install required packages
apt-get install -y frr traceroute net-tools tcpdump

# Enable IP forwarding
echo 'net.ipv4.ip_forward=1' >> /etc/sysctl.conf
echo 'net.ipv6.conf.all.forwarding=1' >> /etc/sysctl.conf
sysctl -p

# Configure FRR for BGP
cat > /etc/frr/daemons << EOF
bgpd=yes
ospfd=no
ospf6d=no
ripd=no
ripngd=no
isisd=no
pimd=no
ldpd=no
nhrpd=no
eigrpd=no
babeld=no
sharpd=no
pbrd=no
bfdd=no
fabricd=no
vrrpd=no
EOF

# Configure BGP
cat > /etc/frr/frr.conf << EOF
!
frr version 8.1
frr defaults traditional
hostname nva-vm
log syslog informational
no ipv6 forwarding
service integrated-vtysh-config
!
router bgp ${bgp_asn}
 bgp router-id ${nva_private_ip}
 bgp log-neighbor-changes
 bgp bestpath as-path multipath-relax$(if [ -n "${route_server_ip_1}" ]; then echo "
 neighbor ${route_server_ip_1} remote-as 65515
 neighbor ${route_server_ip_1} ebgp-multihop 255"; fi)$(if [ -n "${route_server_ip_2}" ]; then echo "
 neighbor ${route_server_ip_2} remote-as 65515
 neighbor ${route_server_ip_2} ebgp-multihop 255"; fi)
 !
 address-family ipv4 unicast$(for route in ${bgp_advertised_routes}; do echo "
  network $route"; done)$(if [ -n "${route_server_ip_1}" ]; then echo "
  neighbor ${route_server_ip_1} activate"; fi)$(if [ -n "${route_server_ip_2}" ]; then echo "
  neighbor ${route_server_ip_2} activate"; fi)
 exit-address-family
!
line vty
!
EOF

# Set proper permissions
chown frr:frr /etc/frr/frr.conf
chmod 640 /etc/frr/frr.conf

# Enable and start FRR
systemctl enable frr
systemctl start frr

# Create status script
cat > /home/${nva_admin_username}/check_bgp.sh << 'EOF'
#!/bin/bash
echo "=== BGP Summary ==="
sudo vtysh -c "show bgp summary"
echo ""
echo "=== BGP Routes ==="
sudo vtysh -c "show ip route bgp"
echo ""
echo "=== System Routes ==="
ip route show
EOF

chmod +x /home/${nva_admin_username}/check_bgp.sh

# Create configuration script for adding custom routes
cat > /home/${nva_admin_username}/add_routes.sh << EOF

#!/bin/bash
# Current configured BGP routes:
$(for route in ${bgp_advertised_routes}; do echo "# - $route"; done)

# Example: Add a custom route to advertise
# sudo vtysh -c "configure terminal" -c "router bgp ${bgp_asn}" -c "address-family ipv4 unicast" -c "network 10.20.0.0/16"

echo "Current BGP ASN: ${bgp_asn}"
echo "Currently configured routes:"
$(for route in ${bgp_advertised_routes}; do echo "echo \"  - $route\""; done)
echo ""
echo "To add a new route:"
echo "sudo vtysh -c \"configure terminal\" -c \"router bgp ${bgp_asn}\" -c \"address-family ipv4 unicast\" -c \"network <new_network>\""
echo ""
echo "To remove a route:"
echo "sudo vtysh -c \"configure terminal\" -c \"router bgp ${bgp_asn}\" -c \"address-family ipv4 unicast\" -c \"no network <network>\""
EOF

chmod +x /home/${nva_admin_username}/add_routes.sh

# Install Azure CLI for management
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash

# Log completion
echo "NVA configuration completed at $(date)" >> /var/log/nva-setup.log

sudo reboot