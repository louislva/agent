#!/usr/bin/env python3
"""
Agent VM - Minimalist agentic coding tool
Usage: python agent.py [init|edit|build]
"""

import os
import json
import time
import secrets
import string
import subprocess
from pathlib import Path
from typing import TypedDict

try:
    from linode_api4 import LinodeClient, Instance, Image
except ImportError:
    print("Please install: pip install linode-api4")
    exit(1)

class Config(TypedDict):
    repo_name: str
    base_image_id: str
    instance_type: str
    created_at: int
    root_password: str

class AgentVM:
    def __init__(self):
        self.config_file = '.agentconfig'
        self.repo_name = Path.cwd().name
        
        # Get Linode token from environment
        token = os.getenv('LINODE_TOKEN')
        if not token:
            self._setup_token()
            exit(1)
            
        self.linode = LinodeClient(token)
        
    def _setup_token(self):
        """Interactive token setup"""
        print("❌ No LINODE_TOKEN found in environment")
        print()
        print("📝 To get your Linode API token:")
        print("   1. Go to: https://cloud.linode.com/profile/tokens")
        print("   2. Click 'Create Token'")
        print("   3. Give it a label like 'agent-vm-tool'")
        print("   4. Set scopes to '*' (all permissions)")
        print("   5. Copy the token")
        print()
        
        token = input("🔑 Paste your Linode token here: ").strip()
        
        if not token:
            print("❌ No token provided")
            return
            
        # Detect shell and OS
        shell = os.environ.get('SHELL', '/bin/bash').split('/')[-1]
        home = os.path.expanduser('~')
        
        if shell == 'zsh':
            profile_file = f"{home}/.zshrc"
        elif shell == 'bash':
            profile_file = f"{home}/.bashrc"
        else:
            profile_file = f"{home}/.profile"
            
        print(f"\n💾 Adding LINODE_TOKEN to {profile_file}")
        
        # Add to profile file
        export_line = f'export LINODE_TOKEN="{token}"\n'
        
        try:
            with open(profile_file, 'a') as f:
                f.write(f'\n# Agent VM tool\n{export_line}')
            
            print("✅ Token added to your shell profile!")
            print(f"\n🔄 Run this to reload your shell:")
            print(f"   source {profile_file}")
            print("\n   OR open a new terminal window")
            print("\n🚀 Then run 'python agent.py init' again")
            
        except Exception as e:
            print(f"❌ Failed to write to {profile_file}: {e}")
            print(f"\n📋 Manually add this line to {profile_file}:")
            print(f"   {export_line}")
            print(f"\n🔄 Then run: source {profile_file}")
        
    def _wait_for_boot(self, instance: Instance):
        """Wait for instance to boot and be SSH-ready"""
        import sys
        
        start_time = time.time()
        last_status = None
        status_start_time = start_time
        
        # Wait for instance to be running
        while instance.status != 'running':
            time.sleep(5)
            instance = self.linode.linode.instances(Instance.id == instance.id)[0]
            
            # Track status changes
            if instance.status != last_status:
                if last_status is not None:
                    print()  # New line when status changes
                last_status = instance.status
                status_start_time = time.time()
            
            # Show current status with time in that status
            elapsed_in_status = int(time.time() - status_start_time)
            total_elapsed = int(time.time() - start_time)
            
            print(f"\r⏳ Status: {instance.status} ({elapsed_in_status}s) | Total: {total_elapsed}s", end='', flush=True)
        
        # Wait for SSH to be ready
        print(f"\n⏳ Status: ssh_ready (0s) | Total: {int(time.time() - start_time)}s", end='', flush=True)
        ssh_start = time.time()
        
        for i in range(30):
            time.sleep(1)
            ssh_elapsed = int(time.time() - ssh_start)
            total_elapsed = int(time.time() - start_time)
            print(f"\r⏳ Status: ssh_ready ({ssh_elapsed}s) | Total: {total_elapsed}s", end='', flush=True)
            
        print("\n✅ VM is ready!")
    
    def _wait_for_image(self, image: Image):
        """Wait for image to be ready"""
        print("🖼️  Waiting for image to be ready...")

        wait_time = 0
        max_wait_time = 600  # 10 minutes max for image creation
        
        while image.status != 'available':
            time.sleep(10)
            wait_time += 10
            image._api_get()
            
            # Calculate percentage based on typical image creation time
            percentage = min(int((wait_time / max_wait_time) * 95), 95)
            print(f"   Status: {image.status.title()} ({percentage}%)")
            
            if wait_time >= max_wait_time:
                print("⚠️  Image creation taking longer than expected...")
                break
            
        print("✅ Image is ready! (100%)")

    def _save_config(self, config):
        """Save configuration to .agentconfig"""
        with open(self.config_file, 'w') as f:
            json.dump(config, f, indent=2)
            
    def _load_config(self):
        """Load configuration from .agentconfig"""
        if not os.path.exists(self.config_file):
            return {}
        with open(self.config_file, 'r') as f:
            return json.load(f)
            
    def _interactive_session(self, config: Config, instance: Instance, session_type="editing"):
        """Show SSH details and wait for user to save or cancel"""
        ip = instance.ipv4[0]
        
        print(f"""
🚀 VM Ready for {session_type}!

SSH Details:
  Host: {ip}
  User: root
  Password: {config['root_password']}

SSH Command:
  ssh root@{ip}

VS Code Remote:
  ssh://root@{ip}

When you're done configuring:
  [Enter] Save and exit
  [Ctrl+C] Cancel and destroy VM
""")
        
        try:
            input("Press Enter when ready to save...")
            return True  # User wants to save
        except KeyboardInterrupt:
            print("\n🗑️  Cancelling and destroying VM...")
            return False  # User cancelled
        
    def init_project(self):
        """Initialize new agent environment"""
        if os.path.exists(self.config_file):
            print("❌ Project already initialized. Use 'agent edit' to modify.")
            return
            
        print("🚀 Initializing new agent environment...")

        # Save config
        config: Config = {
            'repo_name': self.repo_name,
            'base_image_id': 'linode/ubuntu22.04',
            'instance_type': 'g6-nanode-1', # $5/month instance
            'created_at': int(time.time()),
            'root_password': Instance.generate_root_password()
        }
        self._save_config(config)

    def _create_vm(self, config: Config):        
        # Create VM
        try:
            instance = self.linode.linode.instance_create(
                ltype=config['instance_type'],
                region='us-east',
                image=config['base_image_id'],
                root_pass=config['root_password'],
                authorized_keys=["~/.ssh/id_rsa.pub"]
            )
        except Exception as e:
            print(f"❌ Failed to create VM: {e}")
            return
            
        print(f"✅ VM created: {instance.label}")
        return instance
            
    def edit_environment(self):
        """Edit existing environment"""
        config = self._load_config()
        
        if not config.get('base_image_id'):
            print("❌ No environment found. Run 'agent init' first.")
            return
            
        print("🔧 Spinning up environment for editing...")

        # Spin up an instance
        instance = self._create_vm(config)
        self._wait_for_boot(instance)

        try:            
            # Interactive setup session
            should_save = self._interactive_session(config, instance, "setup")
            
            if should_save:
                print("💾 Saving configured environment...")
                
                # Create image from VM
                disk_id = instance.disks[0].id
                image = self.linode.images.create(
                    disk_id,
                    label=f"agent-{self.repo_name}-base"
                )
                self._wait_for_image(image)

                print("✅ Environment saved!")
                config['base_image_id'] = image.__getattribute__("id")
                self._save_config(config)
        finally:
            # Always clean up the temporary VM
            print("🧹 Cleaning up temporary VM...")
            instance.delete()
            
    def _setup_git_credentials(self, config: Config, instance: Instance):
        """Copy git credentials from local machine to VM"""
        ip = instance.ipv4[0]
        home = os.path.expanduser('~')
        
        print("🔑 Setting up git credentials...")
        
        # Create .ssh directory on VM
        self._ssh(config, instance, "mkdir -p /root/.ssh && chmod 700 /root/.ssh")
        
        # Copy SSH keys if they exist
        ssh_files_to_copy = []
        potential_keys = ['id_rsa', 'id_rsa.pub', 'id_ed25519', 'id_ed25519.pub', 'config', 'known_hosts']
        
        for key_file in potential_keys:
            local_key_path = os.path.join(home, '.ssh', key_file)
            if os.path.exists(local_key_path):
                ssh_files_to_copy.append(key_file)
        
        if ssh_files_to_copy:
            print(f"📋 Copying SSH keys: {', '.join(ssh_files_to_copy)}")
            
            # Use rsync to copy SSH files
            ssh_rsync_cmd = [
                'rsync',
                '-avz',
                '-e', 'ssh -o StrictHostKeyChecking=no',
                *[os.path.join(home, '.ssh', f) for f in ssh_files_to_copy],
                f'root@{ip}:/root/.ssh/'
            ]
            
            try:
                result = subprocess.run(ssh_rsync_cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    print("✅ SSH keys copied successfully")
                    
                    # Set proper permissions for private keys
                    self._ssh(config, instance, "chmod 600 /root/.ssh/id_* 2>/dev/null || true")
                    self._ssh(config, instance, "chmod 644 /root/.ssh/*.pub 2>/dev/null || true")
                    self._ssh(config, instance, "chmod 644 /root/.ssh/config 2>/dev/null || true")
                    self._ssh(config, instance, "chmod 644 /root/.ssh/known_hosts 2>/dev/null || true")
                else:
                    print("⚠️  SSH key copy failed:", result.stderr.strip())
            except Exception as e:
                print(f"⚠️  SSH key copy failed: {e}")
        else:
            print("⚠️  No SSH keys found in ~/.ssh/")
            
        # Copy git config if it exists
        gitconfig_path = os.path.join(home, '.gitconfig')
        if os.path.exists(gitconfig_path):
            print("📋 Copying git configuration...")
            
            git_rsync_cmd = [
                'rsync',
                '-avz',
                '-e', 'ssh -o StrictHostKeyChecking=no',
                gitconfig_path,
                f'root@{ip}:/root/.gitconfig'
            ]
            
            try:
                result = subprocess.run(git_rsync_cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    print("✅ Git configuration copied successfully")
                else:
                    print("⚠️  Git config copy failed:", result.stderr.strip())
            except Exception as e:
                print(f"⚠️  Git config copy failed: {e}")
        else:
            print("⚠️  No .gitconfig found, setting up basic git config...")
            
            # Try to get git config from local machine
            try:
                name_result = subprocess.run(['git', 'config', 'user.name'], capture_output=True, text=True)
                email_result = subprocess.run(['git', 'config', 'user.email'], capture_output=True, text=True)
                
                if name_result.returncode == 0 and email_result.returncode == 0:
                    name = name_result.stdout.strip()
                    email = email_result.stdout.strip()
                    
                    if name and email:
                        self._ssh(config, instance, f'git config --global user.name "{name}"')
                        self._ssh(config, instance, f'git config --global user.email "{email}"')
                        print(f"✅ Set git user: {name} <{email}>")
                    else:
                        print("⚠️  Local git user.name or user.email not configured")
                else:
                    print("⚠️  Could not read local git configuration")
            except Exception as e:
                print(f"⚠️  Failed to setup git config: {e}")
        
        # Test git/SSH setup
        print("🧪 Testing git setup...")
        result = self._ssh(config, instance, "ssh -o StrictHostKeyChecking=no -T git@github.com")
        if result and "successfully authenticated" in result.stderr:
            print("✅ GitHub SSH authentication working!")
        else:
            print("⚠️  GitHub SSH test inconclusive (this might be normal)")

    def build_session(self, instance_id=None):
        """Start a build session"""
        config = self._load_config()
        
        if not config.get('base_image_id'):
            print("❌ No environment found. Run 'agent init' first.")
            return
            
        try:
            if instance_id:
                print(f"🔗 Connecting to existing VM (ID: {instance_id})...")
                
                # Fetch existing instance
                instance = self.linode.linode.instances(Instance.id == int(instance_id))[0]
                print(f"✅ Found existing VM: {instance.label}")
            else:
                print("🤖 Starting build session...")
                
                # Spin up an instance
                instance = self._create_vm(config)
                self._wait_for_boot(instance)
            
            ip = instance.ipv4[0]
            
            # Example: Sync current repo to VM
            # Setup git credentials
            # self._setup_git_credentials(config, instance)
            # self._rsync(config, instance)
            
            # Example: Sync specific folder to custom path
            # self._rsync(config, instance, local_path="./src", remote_path="/root/project")
            
            # Example: Run setup commands after sync
            # self._ssh(config, instance, "date >> auto.txt")
            # self._ssh(config, instance, "apt update && apt install -y htop")
            # self._ssh(config, instance, "bash /root/code/setup.sh")
            
            print(f"""
🚀 VM Ready!

SSH Details:
  Host: {ip}
  User: root
  Password: {config['root_password']}

SSH Command:
  ssh root@{ip}

VS Code Remote:
  ssh://root@{ip}

Git Credentials: ✅ Configured
  • SSH keys copied from ~/.ssh/
  • Git config copied from ~/.gitconfig

When you're done configuring:
  [Enter] Save and exit
  [Ctrl+C] Cancel and destroy VM
""")
            
            self._ssh(config, instance)
                
        except Exception as e:
            print(f"❌ Failed to create VM: {e}")
            print("You may want to delete the VM manually: https://cloud.linode.com/linodes")

    def _ssh(self, config: Config, instance: Instance, command=None):
        """SSH to instance - either interactive session or execute command"""
        ip = instance.ipv4[0]
        
        if command:
            # Execute a specific command and return result
            ssh_cmd = f"ssh -o StrictHostKeyChecking=no root@{ip} '{command}'"
            print(f"🔧 Executing: {command}")
            
            try:
                result = subprocess.run(ssh_cmd, shell=True, capture_output=True, text=True)
                if result.stdout:
                    print("Output:", result.stdout.strip())
                if result.stderr:
                    print("Errors:", result.stderr.strip())
                return result
            except Exception as e:
                print(f"⚠️  Command failed: {e}")
                return None
        else:
            # Open interactive SSH session
            ssh_cmd = f"ssh -o StrictHostKeyChecking=no root@{ip}"
            print("🚀 SSH session starting...")
            subprocess.run(ssh_cmd, shell=True)

    def _rsync(self, config: Config, instance: Instance, local_path=None, remote_path="/root/code", exclude_patterns=None):
        """Rsync files from local to remote VM"""
        ip = instance.ipv4[0]
        
        # Default to current working directory if no local path specified
        if local_path is None:
            local_path = os.getcwd()
            
        # Ensure local path ends with / for rsync behavior
        if not local_path.endswith('/'):
            local_path += '/'
            
        # Default exclude patterns
        if exclude_patterns is None:
            exclude_patterns = [
                '.git/',
                '__pycache__/',
                '*.pyc',
                '.DS_Store',
                'node_modules/',
                '.env',
                '.agentconfig',
                '*.log'
            ]
        
        # Build exclude arguments
        exclude_args = []
        for pattern in exclude_patterns:
            exclude_args.extend(['--exclude', pattern])
        
        # Build rsync command
        rsync_cmd = [
            'rsync',
            '-avz',  # archive, verbose, compress
            '--delete',  # delete files on remote that don't exist locally
            '-e', 'ssh -o StrictHostKeyChecking=no',  # SSH options
            *exclude_args,
            local_path,
            f'root@{ip}:{remote_path}'
        ]
        
        print(f"📁 Syncing {local_path} → root@{ip}:{remote_path}")
        
        try:
            result = subprocess.run(rsync_cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                print("✅ Sync completed successfully")
                if result.stdout:
                    # Show a summary of what was synced
                    lines = result.stdout.strip().split('\n')
                    file_count = len([line for line in lines if line and not line.startswith('building') and not line.startswith('sent')])
                    if file_count > 0:
                        print(f"📊 Synced {file_count} files/directories")
            else:
                print("❌ Sync failed")
                if result.stderr:
                    print("Errors:", result.stderr.strip())
                    
            return result
            
        except Exception as e:
            print(f"⚠️  Rsync failed: {e}")
            return None

def main():
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python agent.py [init|edit|build [--continue <linode_id>]]")
        return
        
    command = sys.argv[1]
    agent = AgentVM()
    
    if command == 'init':
        agent.init_project()
    elif command == 'edit':
        agent.edit_environment()
    elif command == 'build':
        # Check for --continue flag
        if len(sys.argv) >= 4 and sys.argv[2] == '--continue':
            instance_id = sys.argv[3]
            agent.build_session(instance_id=instance_id)
        elif len(sys.argv) == 2:
            agent.build_session()
        else:
            print("Usage for build: python agent.py build [--continue <linode_id>]")
    else:
        print("Unknown command. Use: init, edit, or build")


if __name__ == '__main__':
    main()