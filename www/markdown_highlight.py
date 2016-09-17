import mistune
from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters.html import HtmlFormatter

class HighlightRenderer(mistune.Renderer):
    def block_code(self, code, lang):
        guess = 'python3'
        if code.lstrip().startswith('<?php'):
            guess = 'php'
        elif code.lstrip().startswith('<'):
            guess = 'html'
        elif code.lstrip().startswith(('function', 'var', '$')):
            guess = 'javascript'

        lexer = get_lexer_by_name(lang or guess, stripall=True)
        return highlight(code, lexer, HtmlFormatter())

markdown_highlight = mistune.Markdown(renderer=HighlightRenderer(), hard_wrap=True)