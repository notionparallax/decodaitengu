import sys
import os.path
import sphinx_rtd_theme

import decodaitengu

sys.path.append(os.path.abspath('.'))
sys.path.append(os.path.abspath('doc'))

extensions = [
    'sphinx.ext.autodoc', 'sphinx.ext.autosummary', 'sphinx.ext.doctest',
    'sphinx.ext.todo', 'sphinx.ext.viewcode', 'sphinx.ext.mathjax'
]
project = 'decodaitengu'
source_suffix = '.rst'
master_doc = 'index'

version = release = decodaitengu.__version__
copyright = 'DecoDaiTengu Team'

epub_basename = 'decodaitengu - {}'.format(version)
epub_author = 'DecoDaiTengu Team'

todo_include_todos = True

html_theme = 'sphinx_rtd_theme'
html_static_path = ['static']
html_theme_path = [sphinx_rtd_theme.get_html_theme_path()]
html_style = 'decotengu.css'


# vim: sw=4:et:ai
