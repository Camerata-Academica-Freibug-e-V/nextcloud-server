SHELL = /bin/bash

# SPDX-FileCopyrightText: 2018, 2026 Nextcloud GmbH and Nextcloud contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
all: clean dev-setup build-js-production

dev: clean dev-setup build-js
	npm run postbuild

# Dev env management
dev-setup: clean npm-init

npm-init:
#	npm install
#	npm audit fix || true
#	npm update browserslist
	npm ci

npm-update:
	npm update

# Building
build-js:
	npm run dev

build-js-production:
	npm run build

watch-js:
	npm run watch

# Linting
lint-fix:
	npm run lint:fix

lint-fix-watch:
	npm run lint:fix-watch

# Cleaning
clean:
	rm -rf dist

clean-git: clean
	git checkout -- dist

commit-cjh:
	git commit -m "Update package-lock.json" package-lock.json || true
	git add dist
	git add\
 apps/settings/css/settings.css\
 apps/settings/css/settings.css.map\
 core/css/server.css\
 core/css/server.css.map\
 core/css/tooltip.css\
 core/css/tooltip.css.map
	git commit -m "Update assets" || true
	git commit -m "Update 3rdparty/ submodule after bugfix" 3rdparty/ || true

occ-upgrade:
	./occ upgrade
	./occ app:update --all
	./occ maintenance:update:htaccess
	./occ maintenance:mimetype:update-js
	./occ maintenance:mode --off
	chmod g+w config/config.php

VERSION = $(shell grep VersionString version.php|sed -E "s/^.*VersionString = '([0-9]+).*$$/\1/g")

doc:
	set -euo pipefail; \
	mkdir -p tmp build/artifacts/doc; \
	git clone --branch stable$(VERSION) https://github.com/nextcloud/documentation.git tmp/documentation; \
	cd tmp/documentation; \
	python -m venv venv; \
	source venv/bin/activate; \
	pip install -r requirements.txt; \
	$(MAKE) admin-manual-html user-manual-html; \
	mkdir -p archive/admin archive/user; \
	rsync -a --exclude .buildinfo admin_manual/_build/html/com/ archive/admin/; \
	rsync -a --exclude .buildinfo user_manual/_build/html/ archive/user/; \
	find archive/user -name "*.html" -exec sed -i 's|href="/server/latest/user_manual|href="/core/doc/user|g' {} \; ; \
	tar -czf ../../build/artifacts/doc/documentation-$(VERSION).tar.gz -C archive admin user
	rm -rf tmp/documentation

SRCDIR := $(CURDIR)
TOOLDIR := $(SRCDIR)/build
WORKDIR := $(SRCDIR)/tmp
DISTDIR := $(WORKDIR)/$(shell date +%Y-%m-%d)

OVERRIDE_CMDS := --build-command="richdocuments=krankerl package"

distribution:
	mkdir -p $(DISTDIR)
	git checkout $(SRCDIR)/config/CAN_INSTALL || true
# server package
	$(TOOLDIR)/make-nextcloud-dist.sh $(SRCDIR) $(DISTDIR)
# appstore apps
	$(TOOLDIR)/pack-apps.sh -c \
	--only :enabled \
	--exclude :git \
	-d $(DISTDIR) \
	-s $(DISTDIR)/apps-no-git
# git appstore apps
	$(TOOLDIR)/pack-apps.sh -c \
	--only :enabled \
	--exclude :no-git \
	-d $(DISTDIR) \
	-s $(DISTDIR)/apps-git \
	$(OVERRIDE_CMDS)
# git legacy apps (no apparant appstore target)
	$(TOOLDIR)/pack-apps.sh -c \
	--only :enabled \
	--exclude :no-git,:no-legacy \
	-d $(DISTDIR) \
	-s $(DISTDIR)/apps-git-legacy \
	$(OVERRIDE_CMDS)

distribution-clean:
	rm -rf $(DISTDIR)
