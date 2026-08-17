import re

from markdown.extensions import Extension
from markdown.inlinepatterns import InlineProcessor
from markdown.preprocessors import Preprocessor

from xml.etree.ElementTree import Element



#
# Creates the HTML span for every entity
#
# Example output:
#
# <span class="entity entity-vector entity-scope-local"
#       data-entity="TotalForce"
#       data-type="vector"
#       data-scope="local"
#       data-description="The total force">
#     TotalForce
# </span>
#

def make_entity_span(
    entity,
    variable_type,
    scope,
    description=""
):

    span = Element(
        "span",
        {
            "class":
                f"entity "
                f"entity-{variable_type} "
                f"entity-scope-{scope}",

            "data-entity": entity,
            "data-type": variable_type,
            "data-scope": scope,
            "data-description": description,
        }
    )

    span.text = entity

    return span





#
# PASS 1
#
# Collect definitions before Markdown renders variables.
#
# This is what fixes snippets.
#
# Example:
#
# {{!TotalForce:vector:local:"The total accumulated force"}}
#
# becomes:
#
# definitions["TotalForce"] = {
#     type: vector,
#     scope: local,
#     description: The total accumulated force
# }
#

class EntityDefinitionCollector(Preprocessor):

    def __init__(
        self,
        md,
        plugin
    ):

        super().__init__(md)

        self.plugin = plugin



    def run(
        self,
        lines
    ):

        text = "\n".join(lines)


        pattern = re.compile(
            r'\{\{!'
            r'([^}:]+)'
            r'(?::([^}:]+))?'
            r'(?::([^}:]+))?'
            r':"([^"]*)"'
            r'\}\}'
        )


        for match in pattern.finditer(text):

            entity = match.group(1).strip()


            self.plugin.definitions[entity] = {

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


        #
        # Do not remove the definition text.
        # The inline processor below will
        # convert it into an entity.
        #

        return lines





#
# Handles:
#
# {{!Variable:type:scope:"Description"}}
#
# This displays the definition as a normal variable.
#
# The definition has already been stored by
# EntityDefinitionCollector.
#

class EntityDefinitionProcessor(InlineProcessor):

    def __init__(
        self,
        pattern,
        plugin
    ):

        super().__init__(pattern)

        self.plugin = plugin



    def handleMatch(
        self,
        m,
        data
    ):

        entity = m.group(1).strip()


        definition = self.plugin.definitions.get(
            entity,
            {}
        )


        variable_type = definition.get(
            "type",
            "default"
        )


        scope = definition.get(
            "scope",
            "default"
        )


        description = definition.get(
            "description",
            ""
        )


        return (
            make_entity_span(
                entity,
                variable_type,
                scope,
                description,
            ),
            m.start(0),
            m.end(0),
        )







#
# Handles:
#
# {{Variable}}
#
# and:
#
# {{Variable:type:scope}}
#
#
# If a definition exists:
#
# {{Variable}}
#
# inherits:
#
# type
# scope
# description
#
#
# If explicit type/scope are provided:
#
# {{Variable:float:function}}
#
# only type/scope are overridden.
# The description is still inherited.
#

class EntityReferenceProcessor(InlineProcessor):

    def __init__(
        self,
        pattern,
        plugin
    ):

        super().__init__(pattern)

        self.plugin = plugin



    def handleMatch(
        self,
        m,
        data
    ):

        entity = m.group(1).strip()


        definition = self.plugin.definitions.get(
            entity
        )



        #
        # Use explicit type/scope if provided.
        #

        if m.group(2) or m.group(3):

            variable_type = (
                m.group(2).strip()
                if m.group(2)
                else (
                    definition["type"]
                    if definition
                    else "default"
                )
            )


            scope = (
                m.group(3).strip()
                if m.group(3)
                else (
                    definition["scope"]
                    if definition
                    else "default"
                )
            )



        #
        # Otherwise inherit everything.
        #

        elif definition:

            variable_type = definition["type"]

            scope = definition["scope"]



        #
        # Unknown variable.
        #

        else:

            variable_type = "default"

            scope = "default"



        #
        # Description always comes from
        # the stored definition.
        #

        description = (
            definition["description"]
            if definition
            else ""
        )


        return (
            make_entity_span(
                entity,
                variable_type,
                scope,
                description,
            ),
            m.start(0),
            m.end(0),
        )







class EntityExtension(Extension):

    def extendMarkdown(
        self,
        md,
        plugin
    ):


        #
        # PASS 1:
        #
        # Collect all definitions first.
        #
        # Priority 25 means this happens
        # before inline processing.
        #

        md.preprocessors.register(
            EntityDefinitionCollector(
                md,
                plugin
            ),
            "entity_definition_collector",
            25,
        )



        #
        # PASS 2:
        #
        # Render definition variables.
        #

        md.inlinePatterns.register(
            EntityDefinitionProcessor(
                (
                    r"\{\{!"
                    r"([^}:]+)"
                    r"(?::([^}:]+))?"
                    r"(?::([^}:]+))?"
                    r':"([^"]*)"'
                    r"\}\}"
                ),
                plugin,
            ),
            "entity_definition",
            200,
        )



        #
        # PASS 2:
        #
        # Render normal variables.
        #

        md.inlinePatterns.register(
            EntityReferenceProcessor(
                (
                    r"\{\{"
                    r"([^}:!]+)"
                    r"(?::([^}:]+))?"
                    r"(?::([^}:]+))?"
                    r"\}\}"
                ),
                plugin,
            ),
            "entity_reference",
            175,
        )





def makeExtension(**kwargs):

    return EntityExtension(**kwargs)
