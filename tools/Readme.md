
# Develop a new plugin/tool

Create a new branch to begin.

Inside tools folder, create a new folder for the tool. Create a file to define the tool that inherits the `BaseTool` class:

```python
from ..base import BaseTool
class YourTool(BaseTool):
    name: str # the name of the tool that communicates its purpose
    description: str # used to tell the model how/when/why to use the tool. You can provide few-shot examples as a part of the description.
    user_description: str # similar to description, but a concise version, shown to the user
    usable_by_bot: bool = True # whether or not the tool is used by the bot duirng chat
    disable_all_other_tools: bool = False # when using this tool, should all other tools be disabled?
    def __init__(self, func: Callable=None, **kwargs) -> None:
        '''
        If you want to have the parameters configurable, you need to inform the dev team in your PR, so the dev team can properly configure it in the actual code that uses the tool. 
        However, you should not rely on the func argument here, implement your main logic in `_run` instead.
        predefined_params = kwargs.get("param_name", 3)
        '''
        super().__init__(None)
        '''
        Add additional information so that the bot knows what each parameter is used for and which of them are required. 
        This must be after super().__init__() where the arguments are parsed properly.

        self.args["properties"]["req_info"]["description"] = "User's current location. If you don't know user's location, you should still include empty dict {} as req_info in the arguments"
        self.args["properties"]["query"]["description"] = "The string used to search. Make it as concise as possible"
        self.args["required"] = ["query", "req_info"]
        '''
    
    def on_enable(self, *args: Any, **kwargs: Any) -> Any:
        '''
        Your logic when the tool is enabled by the user.
        '''
    
    def on_disable(self, *args: Any, **kwargs: Any) -> Any:
        '''
        Your logic when the tool is disabled by the user.
        '''

    def _run(self, query: str, req_info: dict=None):
        '''
        Your main logic unless it is not usable by the bot.
        '''
```

If your code is not usable by the bot (`usable_by_bot=False`), we provide 5 event triggers that can be used to call the functions. Examples of how to use them can be found in the memory tool.

- `OnStartUp`: triggered when the user is just connected to the app. 
- `OnStartUpMsgEnd`: triggered when the user received the startup greetings. Example use in memory.py
- `OnUserMsgReceived`: triggered when the app receives a message from the user websocket.
- `OnResponseEnd`: triggered when the bot finishes the response to the user.
- `OnUserDisconnected`: triggered when the user disconnects.
- `OnModelChanged`: triggered when the user changes the GPT model (GPT3.5, GPT4, finetuned model etc)

The event triggers (except `OnModelChanged``) will receive the following information as keyword arguments from main:
- `user_id`: The user's unique identifier, can be used to index database. 
- `user_info`: General user information generated by `memory` module, contains information such as `name`, `age`, `last_conversation`, etc. For details, check [memory](./memory/memory.py).
- `user_tool_settings`: A dictionary `{tool_name1: True, tool_name2: False}` showing which tools are enabled by the specific user.
- `message`: Dictionary of the format `{"role": "assistant" | "user", "content": msg_content}` recording the most recent assistant/user messages. For `OnStartUp`, it is a dummy variable `{"role": "assistant", "content": ""}`.
- `user_assistants`: A list of methods that update initial prompts of user asssitants. Can be used as `user_assistants[i](information_str)`. 

The `OnModelChanged` event trigger is treated separately and will receive the following information as keyword arguments from main:
- `user_id`: The user's unique identifier, can be used to index database. 
- `current_user_settings`: The current user settings that is a superset of the following dictionary `{"assistantsName", "gptMode", "aiDescription"}`, `gptMode` is the new model type user selected.
- `update_user_settings_fn`: The function to overwrite the current user settings. You are suggested only change the three above mentioned fields.

You should not set `disable_all_other_tools=True`, unless you clearly state why your plugin/tool needs to disable all other tools.

After creating the main functional files, you can (and you should) create some test files under the same folder you define the plugin/tool to show that your plugin/tool is working properly.

## Running and testing the plugins/tools

Whatever changes you make in the `tools` subfolder can be tested in the top level folder `<folder for development>` by the following command:

```bash
python -m tools.<tool_folder>.<test_file_without_extenstion>
```

e.g. we provide a sample test file in `local_search` called `local_search_test.py`, to properly run it, you need to execute the foolowing command in `<folder for development>`:

```bash
python -m tools.local_search.local_search_test
```

If you want to run the sample test file, or use any of the provided tools, you should prepare a `.env` file in `<folder for development>` with the following content:

```bash
OPENAI_KEY= # used for anything related to open ai API
SERPAPI_KEY= # used for web/news search
HOUNDIFY_ID= # used for local search
GOOGLE_MAP_KEY= # used for local search
PINECONE_API_KEY= # used for file processing, requires an index of dimension 1536
PINECONE_API_ENV= # used for file processing
FB_ADMIN= # base64 encoded firebase admin json file, used for database for memory.
# additional KEYs used for other tools/plugins
```

## Integrating new plugin/tool to the chatbot

After you are certain the plugin works as expected, in `tools/__init__.py`:

```python
# other imports
import your_tool

__all__ = [
    ...,
    "class_name_of_your_tool",
]

name_map = {
    ...,
    class_name_of_your_tool.name: "class_name_of_your_tool",
}
```

This will allow the parent package detect and enable the tool.
