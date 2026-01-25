 For GUI apps over SSH, you need X11 forwarding:                                 
                                                                                  
  On your SSH connection:                                                         
  ssh -X user@desktop    # Basic X11 forwarding                                   
  # or                                                                            
  ssh -Y user@desktop    # Trusted X11 forwarding (less secure, but fewer issues) 
                                                                                  
  Then verify:                                                                    
  echo $DISPLAY                                                                   
  # Should show something like localhost:10.0                                     
                                                                                  
  If it's still empty, check:                                                     
                                                                                  
  1. SSH server config (/etc/ssh/sshd_config on desktop):                         
  X11Forwarding yes                                                               
  2. You have xauth installed on the desktop:                                     
  sudo pacman -S xorg-xauth   # Arch                                              
  3. Restart sshd after config changes:                                           
  sudo systemctl restart sshd                                                     
                                                                                  
  Alternative: Wayland forwarding (experimental)                                  
  Wayland doesn't support forwarding like X11. For Wayland apps over SSH, you'd   
  need something like waypipe:                                                    
  # On local machine                                                              
  waypipe ssh user@desktop CloudCompare                                           
                                                                                  
  X11 forwarding is the most reliable option for remote GUI apps. 