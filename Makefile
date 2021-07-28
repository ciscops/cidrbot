# Makefile
PYTHON_EXE = python3
# PROJECT_NAME is used to create the virtualenv name
PROJECT_NAME="cidrbot"
LAMBDA_FUNCTION_NAME="ppajersk-cidrbot"
TOPDIR = $(shell git rev-parse --show-toplevel)
# PYDIRS is where we look for python code that needs to be linted
PYDIRS=wxt_cidrbot
VENV = venv_$(PROJECT_NAME)
VENV_BIN=$(VENV)/bin
SRC_FILES := $(shell find $(PYDIRS) -name \*.py)
SPHINX_DEPS := $(shell find docs/source)
GENERATED_DOC_SOURCES := $(shell find docs/source -maxdepth 1 -type f -name \*.rst -not -name index.rst)

help: ## Display help
	@awk -F ':|##' \
	'/^[^\t].+?:.*?##/ {\
	printf "\033[36m%-30s\033[0m %s\n", $$1, $$NF \
	}' $(MAKEFILE_LIST)

all: clean venv_$(PROJECT_NAME) check test dist ## Setup python-viptela env and run tests

venv: ## Creates the needed virtual environment.
	test -d $(VENV) || virtualenv -p $(PYTHON_EXE) $(VENV) $(ARGS)

$(VENV): $(VENV_BIN)/activate ## Build virtual environment

$(VENV_BIN)/activate: requirements.txt test-requirements.txt
	test -d $(VENV) || virtualenv -p $(PYTHON_EXE) $(VENV)
	echo "export TOP_DIR=$(TOPDIR)" >> $(VENV_BIN)/activate
	. $(VENV_BIN)/activate; pip install -U pip; pip install -r requirements.txt -r test-requirements.txt

deps: venv ## Installs the needed dependencies into the virtual environment.
	$(VENV_BIN)/pip install -U pip
	$(VENV_BIN)/pip install -r requirements.txt -r test-requirements.txt

dev: deps ## Installs python_viptela in develop mode.
	$(VENV_BIN)/pip install -e ./

check-format: $(VENV)/bin/activate ## Check code format
	@( \
	set -eu pipefail ; set -x ;\
	DIFF=`$(VENV)/bin/yapf --style=yapf.ini -d -r *.py $(PYDIRS)` ;\
	if [ -n "$$DIFF" ] ;\
	then \
	echo -e "\nFormatting changes requested:\n" ;\
	echo "$$DIFF" ;\
	echo -e "\nRun 'make format' to automatically make changes.\n" ;\
	exit 1 ;\
	fi ;\
	)

format: $(VENV_BIN)/activate ## Format code
	$(VENV_BIN)/yapf --style=yapf.ini -i -r *.py $(PYDIRS)

pylint: $(VENV_BIN)/activate ## Run pylint
	$(VENV_BIN)/pylint --output-format=parseable --rcfile .pylintrc *.py $(PYDIRS)

check: check-format pylint ## Check code format & lint

build: deps ## Builds EGG info and project documentation.
	$(VENV_BIN)/python setup.py egg_info

dist: build ## Creates the distribution.
	$(VENV_BIN)/python setup.py sdist --formats gztar
	$(VENV_BIN)/python setup.py bdist_wheel


test: deps ## Run python-viptela tests
	. $(VENV_BIN)/activate; pip install -U pip; pip install -r requirements.txt -r test-requirements.txt;tox -r

clean: ## Clean python-viptela $(VENV)
	$(RM) -rf $(VENV)
	$(RM) -rf docs/_build
	$(RM) -rf dist
	$(RM) -rf *.egg-info
	$(RM) -rf *.eggs
	$(RM) -rf docs/api/*
	find . -name "*.pyc" -exec $(RM) -rf {} \;

clean-docs-html:
	$(RM) -rf docs/build/html
clean-docs-markdown:
	$(RM) -rf docs/build/markdown

docs: docs-markdown docs-html ## Generate documentation in HTML and Markdown

docs-markdown: clean-docs-markdown $(SPHINX_DEPS) $(VENV)/bin/activate ## Generate Markdown documentation
	. $(VENV_BIN)/activate ; $(MAKE) -C docs markdown
docs-html: clean-docs-html $(SPHINX_DEPS) $(VENV)/bin/activate ## Generate HTML documentation
	. $(VENV_BIN)/activate ; $(MAKE) -C docs html

docs-clean: ## Clean generated documentation
	$(RM) $(GENERATED_DOC_SOURCES)
	. $(VENV_BIN)/activate ; $(MAKE) -C docs clean

clean-lambda:
	$(RM) -rf lambda-packages
	$(RM) lambda-packages.zip
	$(RM) lambda-function.zip

# create lambda-packages.zip using a docker image
lambda-packages-docker: clean-lambda
	docker run --rm --name lambda-builder --user $$(id -u) -v $$(pwd):/build lambda-builder:latest make lambda-packages.zip

lambda-packages: $(VENV) requirements.txt ## Install all libraries
	@[ -d $@ ] || mkdir -p $@/python # Create the libs dir if it doesn't exist
	. $(VENV_BIN)/activate ; SODIUM_INSTALL=system pip install -r requirements.txt -t $@/python # We use -t to specify the destination of the

	# packages, so that it doesn't install in your virtual env by default

lambda-packages.zip: lambda-packages ## Output all code to zip file
	cd lambda-packages && zip -r ../$@ * # zip all python source code into output.zip

lambda-layer: lambda-packages.zip
	aws lambda publish-layer-version \
	--layer-name $(LAMBDA_FUNCTION_NAME)-layer \
	--license-info "MIT" \
	--zip-file fileb://lambda-packages.zip \
	--compatible-runtimes python3.8

lambda-function.zip: cidrbot_run.py ## Output all code to zip file
	cp cidrbot_run.py lambda_function.py
	zip -r $@ lambda_function.py $(PYDIRS) # zip all python source code into output.zip

lambda-upload:lambda-function.zip ## Deploy all code to aws
	aws lambda update-function-code \
	--function-name $(LAMBDA_FUNCTION_NAME) \
	--zip-file fileb://lambda-function.zip

build-container:
	docker build -t lambda-builder:latest .

.PHONY: all clean $(VENV) test check format check-format pylint clean-docs-html clean-docs-markdown apidocs
