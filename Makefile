SHELL = /bin/bash

# SPDX-FileCopyrightText: 2018 Nextcloud GmbH and Nextcloud contributors
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

doc:
	mkdir -p tmp;\
 cd tmp;\
 rm -rf documentation;\
 git clone https://github.com/nextcloud/documentation.git;\
 cd documentation;\
 git checkout stable31;\
 python -m venv venv;\
 source venv/bin/activate;\
 pip install -r requirements.txt;\
 make admin-manual-html user-manual-html;\
 rsync -a --delete --exclude .buildinfo admin_manual/_build/html/com/. ../../core/doc/admin/.;\
 rsync -a --delete --exclude .buildinfo user_manual/_build/html/. ../../core/doc/user/.
	rm -rf tmp/documentation
	cd core/doc/user/;\
 find . -name "*.html" -exec sed -i 's|href="/server/latest/user_manual|href="/core/doc/user|g' {} \;
