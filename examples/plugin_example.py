"""Example demonstrating the LogzAI plugin system."""
from logzai_otlp import logzai


def simple_plugin(instance, config):
    """Simple plugin that adds a custom logging method."""
    print(f"Simple plugin initialized with config: {config}")

    # Add a custom method to the instance
    def custom_log(message, **kwargs):
        instance.info(f"[CUSTOM] {message}", **kwargs)

    instance.custom_log = custom_log

    # Return cleanup function
    def cleanup():
        print("Simple plugin cleanup")
        if hasattr(instance, 'custom_log'):
            delattr(instance, 'custom_log')

    return cleanup


def request_counter_plugin(instance, config):
    """Plugin that counts log messages."""
    counter = {"count": 0}
    max_count = config.get("max_count", 100) if config else 100

    # Wrap the info method
    original_info = instance.info

    def wrapped_info(message, **kwargs):
        counter["count"] += 1
        kwargs["log_count"] = counter["count"]
        return original_info(message, **kwargs)

    instance.info = wrapped_info

    # Cleanup: restore original method and print stats
    def cleanup():
        instance.info = original_info
        print(f"Request counter plugin: logged {counter['count']} messages (max: {max_count})")

    return cleanup


def main():
    """Demonstrate plugin functionality."""
    # Initialize LogzAI
    logzai.init(
        ingest_token="demo-token",
        ingest_endpoint="http://localhost:4318",
        service_name="plugin-demo",
        mirror_to_console=True
    )

    print("\n--- Registering plugins ---")

    # Register simple plugin
    logzai.plugin("simple", simple_plugin, {"enabled": True})

    # Register counter plugin
    logzai.plugin("counter", request_counter_plugin, {"max_count": 5})

    print("\n--- Using plugin features ---")

    # Use the custom method added by simple plugin
    if hasattr(logzai, 'custom_log'):
        logzai.custom_log("This is a custom log message", user_id="123")

    # Regular logging (wrapped by counter plugin)
    logzai.info("First message", action="test")
    logzai.info("Second message", action="test")
    logzai.info("Third message", action="test")

    print("\n--- Unregistering simple plugin ---")
    logzai.unregister_plugin("simple")

    # This should not work anymore
    if hasattr(logzai, 'custom_log'):
        logzai.custom_log("This won't be logged")
    else:
        print("custom_log method removed after plugin unregistration")

    print("\n--- Shutdown (cleans up remaining plugins) ---")
    logzai.shutdown()

    print("\n--- Done ---")


if __name__ == "__main__":
    main()
