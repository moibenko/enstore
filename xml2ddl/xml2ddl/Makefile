MV=mv
RM=rm -rf
all: xml2ddl
TARGET_DIR=../../bin
XML2DDL_SCRIPTS=diffxml2ddl downloadXml xml2ddl xml2html
.SECONDEXPANSION:
$(XML2DDL_SCRIPTS): $$@
	pyinstaller --onefile --distpath xml2ddl_dist  --workpath xml2ddl_build --hidden-import enroute $@.py
	$(MV) xml2ddl_dist/$@ $(TARGET_DIR)
	$(RM) xml2ddl_dist xml2ddl_build *.spec
xml2ddl: $(XML2DDL_SCRIPTS)

