#!/usr/bin/python
# ----------------------------------------------------------------------------
# cocos "hash" plugin
#
# Copyright 2013 (C) Intel
#
# License: MIT
# ----------------------------------------------------------------------------

'''
"hash" plugin for cocos command line tool
'''

__docformat__ = 'restructuredtext'

import sys
import subprocess
import os
import json
import shutil
import binascii
import time
import zipfile

import cocos
from MultiLanguage import MultiLanguage

def mkdirp(directory):
    if not os.path.isdir(directory):
        os.makedirs(directory)

def crc32(filename):
    a_file = open(filename, 'rb')
    crc = binascii.crc32(a_file.read())
    a_file.close()
    return "%x"%(crc& 0xffffffff)

def make_json(hashitems, major, minor):
    return {
        'version':minor,
        'cpp_version':major,
        'files':hashitems
    }

def is_same_version(old, new):
    return cmp(old, new) == 0

def replace_lua_with_luac(work_dir):
    file_list = os.listdir(work_dir)
    for f in file_list:
        full_path = os.path.join(work_dir, f)
        if os.path.isdir(full_path):
            replace_lua_with_luac(full_path)
        elif os.path.isfile(full_path):
            name, cur_ext = os.path.splitext(f)
            if cur_ext == '.lua':
                os.remove(full_path)
                shutil.move(full_path+'c', full_path)
def eusure_copy(src, dst):
    if os.path.isdir(dst):
        os.remove(dst)
    shutil.copy(src, dst)


class CCPluginHash(cocos.CCPlugin):
    """
    Update resource and script hash file (res/VERSION.json).
    """
    @staticmethod
    def plugin_name():
        return "hash"

    @staticmethod
    def brief_description():
        # returns a short description of this module
        return 'Update resource and script hash file (res/VERSION.json).'
        #return MultiLanguage.get_string('LUACOMPILE_BRIEF')

    # This is not the constructor, just an initializator
    def init(self, options, workingdir):
        with open('res/VERSION.json') as f:
            self.old = json.load(f)
        self._src_dir_arr = self.normalize_path_in_list(options.src_dir_arr)
        self._verbose = options.verbose
        self._workingdir = workingdir
        self._cpp_version = options.cpp_version or self.old['cpp_version']
        self._no_pack = options.no_pack

    def normalize_path_in_list(self, list):
        for i in list:
            tmp = os.path.normpath(i)
            if not os.path.isabs(tmp):
                tmp = os.path.abspath(tmp)
            list[list.index(i)] = tmp
        return list

    def deep_iterate_dir(self, rootDir, entries):
        for lists in os.listdir(rootDir):
            path = os.path.join(rootDir, lists)
            if os.path.isdir(path):
                self.deep_iterate_dir(path, entries)
            elif os.path.isfile(path):
                if '.DS_Store' in path or 'VERSION.json' in path:
                    continue
                entries.append(path)

    def hash_assets(self, files):
        cocos.Logging.debug('hashing assets')
        items = {}
        for src in files:
            for file in files[src]:
                rel = os.path.relpath(file, src)
                items[rel] = crc32(file)

        self.new = make_json(items, self._cpp_version, self.old['version'])

        up_to_date = is_same_version(self.old, self.new)
        if not up_to_date:
            self.new['version'] += 1
        jsonfile = 'VERSION-%d.%d.json' % (self.new['cpp_version'], self.new['version'])
        with open(jsonfile, 'w') as f:
            json.dump(self.new, f, sort_keys=True, indent=2)

        eusure_copy(jsonfile, 'LATEST.json')

        if up_to_date:
            return False# no need to update version file

        eusure_copy(jsonfile, 'res/VERSION.json')
        return True

    def encrypt(self, dir):
        cocos_cmd_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "cocos")
        compile_cmd = "\"%s\" luacompile -s \"%s\" -d \"%s\" --disable-compile -e" % (cocos_cmd_path, dir, dir)
        # run compile command
        self._run_cmd(compile_cmd)
        replace_lua_with_luac(dir)

    def pack_assets(self, files):
        # 1. copy all res and src file into assets directory
        cocos.Logging.debug('copy assets to packing directory')
        copied = []
        assetsdir = '.assets/'
        if os.path.isdir(assetsdir):
            shutil.rmtree(assetsdir)
        for src in files:
            for file in files[src]:
                rel = os.path.relpath(file, src)
                to = assetsdir + rel
                mkdirp(os.path.dirname(to))
                shutil.copy(file, to)
                copied.append(rel)

        # 2. invoke luacompile to compile/encrypt luafiles
        cocos.Logging.debug('encrypt lua files')
        self.encrypt(assetsdir)

        zipname = 'PATCH-%d.%s.zip' % (self.new['cpp_version'], self.new['version'])
        # 3. make zip package
        cocos.Logging.debug('packing assets in to '+zipname)
        z = zipfile.ZipFile(zipname, 'w')
        for f in copied:
            z.write(assetsdir+f, f, compress_type = zipfile.ZIP_DEFLATED)
        z.close()

        eusure_copy(zipname, 'LATEST.zip')

        if os.path.isdir(assetsdir):
            shutil.rmtree(assetsdir)


    def run(self, argv, dependencies):
        self.parse_args(argv)

        if len(subprocess.check_output(['git', 'status', '--porcelain'])) > 0:
            cocos.Logging.error('***Your wroking copy is not clean')
            #sys.exit(1)
        # deep iterate the src directory
        files = {}
        for src_dir in self._src_dir_arr:
            files[src_dir] = []
            self.deep_iterate_dir(src_dir, files[src_dir])

        if not self.hash_assets(files):
            cocos.Logging.info('nothing to update')

        if not self._no_pack:
            self.pack_assets(files)
        cocos.Logging.info('Hash finished.')

    def parse_args(self, argv):
        from argparse import ArgumentParser

        parser = ArgumentParser(prog="cocos %s" % self.__class__.plugin_name(),
                                description=self.__class__.brief_description())

        parser.add_argument("-v", "--verbose", action="store_true", dest="verbose",
                            help=MultiLanguage.get_string('LUACOMPILE_ARG_VERBOSE'))

        parser.add_argument("-s", "--src", dest="src_dir_arr",
                            default=['src', 'res'], action="append",
                            help=MultiLanguage.get_string('LUACOMPILE_ARG_SRC'))

        parser.add_argument("-c", "--cpp", dest="cpp_version",
                            type=int, help='The cpp version')

        parser.add_argument("--no-pack", action="store_true", dest="no_pack",
                            help="don't pack the assets (hash only).")
        options = parser.parse_args(argv)

        if options.src_dir_arr == None:
            raise cocos.CCPluginError(MultiLanguage.get_string('LUACOMPILE_ERROR_SRC_NOT_SPECIFIED'),
                                      cocos.CCPluginError.ERROR_WRONG_ARGS)
        else:
            for src_dir in options.src_dir_arr:
                if os.path.exists(src_dir) == False:
                    raise cocos.CCPluginError(MultiLanguage.get_string('LUACOMPILE_ERROR_DIR_NOT_EXISTED_FMT')
                                              % (src_dir), cocos.CCPluginError.ERROR_PATH_NOT_FOUND)

        # script directory
        if getattr(sys, 'frozen', None):
            workingdir = os.path.realpath(os.path.dirname(sys.executable))
        else:
            workingdir = os.path.realpath(os.path.dirname(__file__))

        self.init(options, workingdir)
