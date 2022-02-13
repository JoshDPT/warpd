#!/usr/bin/env python3

# Copyright © 2019 Raheman Vaiya.
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice (including the next
# paragraph) shall be included in all copies or substantial portions of the
# Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

# cfg.opts should consist of lines of the following form:
# <option/field name> <type (must be string, int, or double)> <default val>

import sys
import re
import glob
import os
import subprocess

h_template = '''//GENERATED BY %s.

#ifndef _CFG_H_
#define _CFG_H_

#include <stddef.h>
#include <unistd.h>
#include <string.h>

struct cfg {
{struct_fields}
};

struct cfg* parse_cfg(const char *fname);

#endif
''' % sys.argv[0]

c_template = r'''//GENERATED BY {script}

#include <stdio.h>
#include <ctype.h>
#include <string.h>
#include <stdlib.h>
#include "{header_file}"

static void parse_list(const char *_s, char ***arr, size_t *sz)
{
	size_t n = 1;
	char **a, *start;
	ssize_t len, i;

	char *s = strdup(_s);
	len = strlen(s);

	for (i = 0; i < len; i++)
		if(s[i] == ',')
			n++;

	a = malloc(n*sizeof(char *));

	n = 0;
	start = s;
	for (i = 0; i < len; i++)
		if(s[i] == ',') {
			s[i++] = 0;
			while(s[i] == ' ')
				i++;

			a[n++] = start;
			start = &s[i];
		}

	a[n++] = start;

	*arr = a;
	*sz = n;
}

static int kvp(char *line, char **key, char **val) {
  *key = NULL;
  *val = NULL;
  
  for(;*line != '\0';line++) {
    if(*line != ' ' && !*key)
      *key = line;
    
    if(*line == ':' && !*val) {
      *line++ = '\0';
      for(;isspace(*line);line++);
      *val = line;
    }
  }
  
  if(*(line - 1) == '\n')
    *(line - 1) = '\0';
  
  if(!(*val && *key))
    return -1;
  
  return 0;
}

struct cfg* parse_cfg(const char *fname) {
    char *line = NULL;
    size_t n = 0, ln = 0;
    struct cfg *cfg = malloc(sizeof(struct cfg));

{field_init}

    FILE *fp = fopen(fname, "r");
    if(!fp) return cfg; //Return defaults if no config file xists..
    while(getline(&line, &n, fp) != -1) {
        ln++;
        char *key, *val;

        if(line[0] == '\n' || line[0] == '\0') continue;

        if(kvp(line, &key, &val)) {
            fprintf(stderr, "Invalid entry in %s at line %lu.\n", fname, ln);
            exit(1);
        }

{field_checks}

        free(line);
        line = NULL;
        n = 0;
    }

    return cfg;
}
'''.replace('{script}', sys.argv[0])


conversion_map = {
    'string': 'cfg->{name} = strdup({input});',
    'int': 'cfg->{name} = atoi({input});',
    'double': 'cfg->{name} = atof({input});',
    'list': 'parse_list({input}, &cfg->{name}, &cfg->{name}_sz);',
}


def generate_h(options):
    struct_fields = ''
    types = {
        'int': 'int\t  ',
        'string': 'char\t *',
        'double': 'double\t  ',
        'list': 'char\t**',
    }

    for fld, typ, _, _ in options:
        struct_fields += '\t%s%s;\n' % (types[typ], fld)
        if typ == "list":
            struct_fields += '\tsize_t\t  %s_sz;\n' % fld

    return h_template.replace('{struct_fields}', struct_fields.rstrip())


def generate_c(options, header_file):
    field_init = ''
    for fld, typ, default, _ in options:
        field_init += "\t" + \
            conversion_map[typ].format(
                name=fld, input="\"%s\"" % default) + "\n"

    field_checks = ''

    cond = 'if'
    for fld, typ, _, _ in options:
        assignment = conversion_map[typ].format(name=fld, input="val")

        field_checks += '''\
        %s(!strcmp(key, "%s"))
            %s\n''' % (cond, fld, assignment)

        cond = 'else if'

    return c_template\
        .replace('{field_checks}', field_checks.rstrip())\
        .replace('{field_init}', field_init.rstrip())\
        .replace('{header_file}', header_file)


def parse_line(l):
    m = re.match('^(\S*)\s+(\S*)\s+"([^"]*)"\s+"([^"]*)"$', l)
    if not m:
        m = re.match('^(\S*)\s+(\S*)\s+(\S*)\s+"([^"]*)"$', l)

    return m[1], m[2], m[3], m[4]


def read_opts(fname):
    ln = 0
    opts = []
    for l in open(fname, 'r').read().rstrip().split('\n'):
        ln += 1
        if l == '':
            continue

        opts.append(parse_line(l))

    return opts


opts = read_opts('cfg.opts')
header = generate_h(opts)
c = generate_c(opts, 'cfg.h')

optstr = ''
for name, _, val, desc in opts:
    optstr += '*%s*: %s (default: %s).\n\n' % (name, desc, val)

print("Generating README.md")
print("man.md")
subprocess.run(["/bin/sh", "-c", "scdoc|gzip > warpd.1.gz"],
        input=open('man.md', 'r').read().replace('{opts}', optstr).encode('utf8'))
print("Generating src/cfg.c")
open('src/cfg.c', 'w').write(c)
print("Generating src/cfg.h")
open('src/cfg.h', 'w').write(header)
