install:
	python -m pip install -e .

test:
	python -m pytest -q

discover:
	wq-evoforge discover

once:
	wq-evoforge once

live-test-one:
	wq-evoforge live-test-one

run:
	wq-evoforge run
