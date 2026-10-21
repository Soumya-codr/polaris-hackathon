"""Public compatibility check, not the scored benchmark: python smoke_test.py URL."""
import asyncio
import json
import sys

from jsonschema import Draft202012Validator
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from search import INPUT_SCHEMA, OUTPUT_SCHEMA


async def main(url):
    async with streamable_http_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            assert init.protocolVersion == '2025-11-25', init.protocolVersion
            listed = await session.list_tools()
            assert [t.name for t in listed.tools] == ['search_products']
            tool = listed.tools[0]
            assert tool.inputSchema == INPUT_SCHEMA
            assert tool.outputSchema == OUTPUT_SCHEMA
            Draft202012Validator.check_schema(tool.inputSchema)
            Draft202012Validator.check_schema(tool.outputSchema)
            for arguments in [{}, {'filters': {'color': 'Black', 'max_price': 2000},
                                    'sort_by': 'price', 'sort_order': 'asc', 'limit': 5},
                                   {'query': 'spaceship engine'},
                                   {'query': 'cotton', 'include_recommendations': True}]:
                result = await session.call_tool('search_products', arguments)
                assert not result.isError, result
                Draft202012Validator(OUTPUT_SCHEMA).validate(result.structuredContent)
                assert json.loads(result.content[0].text) == result.structuredContent
                assert len(result.structuredContent['results']) <= arguments.get('limit', 10)
                if arguments.get('query') == 'spaceship engine':
                    assert result.structuredContent == {'results': [], 'recommendations': []}
            for arguments in [{'limit': 0}, {'filters': {'min_price': 5, 'max_price': 1}},
                              {'filters': {'color': ' '}}, {'extra': 'field'}]:
                result = await session.call_tool('search_products', arguments)
                assert result.isError, result
    print('PASS: MCP initialization, exact schemas, structured JSON responses, search, and validation')


if __name__ == '__main__':
    asyncio.run(asyncio.wait_for(main(sys.argv[1] if len(sys.argv) > 1 else
                                    'http://127.0.0.1:8000/mcp'), timeout=60))
