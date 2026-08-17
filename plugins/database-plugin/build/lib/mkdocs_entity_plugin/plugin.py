from mkdocs.plugins import BasePlugin

from .extension import EntityExtension


class EntityPlugin(BasePlugin):

    def __init__(self):
        self.definitions = {}


    def on_page_markdown(
        self,
        markdown,
        **kwargs
    ):

        import re

        self.definitions.clear()


        definition_pattern = re.compile(
            r'\{\{!'
            r'([^}:]+)'
            r'(?::([^}:]+))?'
            r'(?::([^}:]+))?'
            r':"([^"]*)"'
            r'\}\}'
        )


        for match in definition_pattern.finditer(markdown):

            entity = match.group(1).strip()


            self.definitions[entity] = {

                "type":
                    match.group(2).strip()
                    if match.group(2)
                    else "default",

                "scope":
                    match.group(3).strip()
                    if match.group(3)
                    else "default",

                "description":
                    match.group(4).strip(),
            }


        return markdown



    def on_config(self, config):

        plugin = self


        class EntityExtensionWrapper(EntityExtension):

            def extendMarkdown(self, md):

                super().extendMarkdown(
                    md,
                    plugin
                )


        config["markdown_extensions"].append(
            EntityExtensionWrapper()
        )


        return config
