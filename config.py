import json
import os

CONFIG_FILE = 'bot_config.json'

# Default config structure
default_config = {
    'api_id': None,
    'api_hash': None,
    'target_group': None
}

def load_config():
    """Load configuration from file or create new one if not exists"""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return default_config.copy()

def save_config(config):
    """Save configuration to file"""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

def setup_config():
    """Interactive configuration setup"""
    config = load_config()
    
    print("=== Pinterest Bot Configuration ===")
    print("Press Enter to keep current value (shown in brackets)")
    
    # Get API ID
    current_api_id = config.get('api_id', 'Not set')
    api_id = input(f"Enter Telegram API ID [{current_api_id}]: ").strip()
    if api_id:
        config['api_id'] = int(api_id)
    elif config['api_id'] is None:
        raise ValueError("API ID is required for first setup")

    # Get API Hash
    current_api_hash = config.get('api_hash', 'Not set')
    api_hash = input(f"Enter Telegram API Hash [{current_api_hash}]: ").strip()
    if api_hash:
        config['api_hash'] = api_hash
    elif config['api_hash'] is None:
        raise ValueError("API Hash is required for first setup")

    # Get Target Group
    current_target = config.get('target_group', 'Not set')
    target_group = input(f"Enter Target Group ID [{current_target}]: ").strip()
    if target_group:
        config['target_group'] = int(target_group)
    elif config['target_group'] is None:
        raise ValueError("Target Group ID is required for first setup")

    # Save the configuration
    save_config(config)
    print("Configuration saved successfully!")
    return config

# Get configuration, setup if needed
def get_config():
    """Get configuration, run setup if no config exists"""
    try:
        config = load_config()
        if None in config.values():
            config = setup_config()
        return config
    except Exception as e:
        print(f"Error loading configuration: {e}")
        return setup_config()