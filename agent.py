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
        print(f"⏳ Waiting for VM to boot...")
        
        # Wait for instance to be running
        while instance.status != 'running':
            time.sleep(5)
            instance = self.linode.linode.instances(Instance.id == instance.id)[0]
            
        # Wait a bit more for SSH to be ready
        time.sleep(30)
        print("✅ VM is ready!")
    
    def _wait_for_image(self, image: Image):
        """Wait for image to be ready"""
        print("🖼️  Waiting for image to be ready...")

        while image.status != 'available':
            time.sleep(10)
            image._api_get()
            print(f"   Status: {image.status}")
            
        print("✅ Image is ready!")

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

📁 Your repo will be at: /workspace/{self.repo_name}/

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
                root_pass=config['root_password']
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
            
    def build_session(self):
        """Start a build session"""
        config = self._load_config()
        
        if not config.get('base_image_id'):
            print("❌ No environment found. Run 'agent init' first.")
            return
            
        print("🤖 Starting build session...")
        
        # Create VM from saved image
        try:
            instance = self.linode.linode.instance_create(
                ltype=config['instance_type'],
                region='us-east',
                image=config['base_image_id'],
                root_pass=config['root_password']
            )
        except Exception as e:
            print(f"❌ Failed to create VM: {e}")
            return
            
        try:
            self._wait_for_boot(instance)
            
            # Just show SSH details - no saving option
            ip = instance.ipv4[0]
            password = config['root_password']
            
            print(f"""
🤖 Build VM Ready!

SSH Details:
  Host: {ip}
  User: root
  Password: {password}

SSH Command:
  ssh root@{ip}

📁 Your repo: /workspace/{self.repo_name}/

Press Ctrl+C when done to destroy the VM.
""")
            
            # Just wait for Ctrl+C
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\n🗑️  Destroying build VM...")
                
        finally:
            instance.delete()
            print("✅ Build VM destroyed")


def main():
    import sys
    
    if len(sys.argv) != 2:
        print("Usage: python agent.py [init|edit|build]")
        return
        
    command = sys.argv[1]
    agent = AgentVM()
    
    if command == 'init':
        agent.init_project()
    elif command == 'edit':
        agent.edit_environment()
    elif command == 'build':
        agent.build_session()
    else:
        print("Unknown command. Use: init, edit, or build")


if __name__ == '__main__':
    main()