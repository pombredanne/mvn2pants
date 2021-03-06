#!/usr/bin/env python2.7
#
# Unconditionally recreates the generated BUILD.gen and BUILD.aux files
#

import logging
import os
import sys
import time

from pom_handlers import JavaHomesInfo
from pom_utils import PomUtils
from pom_to_build import PomToBuild
from generate_3rdparty import ThirdPartyBuildGenerator
from generate_external_protos import ExternalProtosBuildGenerator
from generation_context import GenerationContext

logger = logging.getLogger(__name__)

_MODULES_TO_SKIP = set(['parents/external-protos'])

class Task(object):
  """Basically a souped-up lambda function which times itself running."""

  class Error(Exception):
    pass

  def __init__(self, name=None, run=None):
    self._run = run or (lambda: None)
    self.name = name or 'Unnamed Task'
    self._time_taken = -1

  def run(self):
    return self._run()

  @property
  def duration(self):
    if self._time_taken < 0:
      raise self.Error('Time cannot be queried before task is run.')
    return self._time_taken

  def __call__(self):
    logger.debug('Starting {0}.'.format(self.name))
    start = time.time()
    value = self.run()
    end = time.time()
    self._time_taken = end - start
    logger.debug('Done with {name} (took {duration:0.03f} seconds).'.format(name=self.name,
                                                                            duration=self.duration))
    return value


class RegenerateAll(object):
  def __init__(self, path, flags):
    self.baseroot = path
    self.flags = flags

  def _clean_generated_builds(self):
    """Removes all generated BUILD files from the source diretory"""
    logger.debug('Removing old generated BUILD.gen and BUILD.aux files')
    os.system(
      "find {root} \( -path '*/.pants.d/*' -prune -path '*/target/*' -prune \) "
      " -o \( -name BUILD.gen -o -name BUILD.aux -o -name jooq_config.gen.xml \) | xargs rm -f"
      .format(root=self.baseroot))

  def _generate_module_list_file(self):
    modules = PomUtils.get_modules()
    context = GenerationContext()
    with open(context.module_list_file, 'w+') as f:
      f.write("# List of modules for pants's reference. This are currently generated directly\n"
              "# from pom.xml, but in the future we can simply use\n"
              "# ./pants filter --target-type=jvm_binary ::\n\n")
      for module in modules:
        f.write('{}\n'.format(module.strip()))

  def _convert_poms(self):
    modules = PomUtils.get_modules()
    logger.debug('Re-generating {count} modules'.format(count=len(modules)))
    # Convert pom files to BUILD files
    context = GenerationContext()
    for module_name in modules:
      if not module_name in _MODULES_TO_SKIP:
        pom_file_name = os.path.join(module_name, 'pom.xml')
        PomToBuild().convert_pom(pom_file_name, rootdir=self.baseroot, generation_context=context)
    context.os_to_java_homes = JavaHomesInfo.from_pom('parents/base/pom.xml',
                                                      self.baseroot).home_map
    # Write jvm platforms and distributions.
    with open(context.generated_ini_file, 'w+') as f:
      f.write('# Generated by regenerate_all.py. Do not hand-edit.\n\n')
      f.write('\n'.join(context.get_pants_ini_gen()))

    local_ini = 'pants-local.ini'
    if not os.path.exists(local_ini):
      with open(local_ini, 'w') as f:
        f.write('\n'.join([
          '# Local pants.ini file, not tracked by git.',
          '# Use this to make your own custom changes/overrides to pants settings.',
          '# Note: This is for local settings only.  Changes you make here will',
          '# not be used in CI (use pants.ini for that).',
          '',
          '# Uncomment to use local build cache ',
          '# (Saves time when switching between branches frequently.)',
          '#[cache]',
          '#read_from: ["~/.cache/pants/local-build-cache"]',
          '#read: True',
          '#write_to: ["~/.cache/pants/local-build-cache"]',
          '#write: True',
          '',
        ]))

  def _regenerate_external_protos(self):
    logger.debug('Re-generating parents/external-protos/BUILD.gen')
    with open('parents/external-protos/BUILD.gen', 'w') as build_file:
      build_file.write(ExternalProtosBuildGenerator().generate())

  def _regenerate_3rdparty(self):
    logger.debug('Re-generating 3rdparty/BUILD.gen')
    with open('3rdparty/BUILD.gen', 'w') as build_file:
      build_file.write(ThirdPartyBuildGenerator().generate())

  def execute(self):
    Task('clean_build_gen', self._clean_generated_builds)()
    Task('generate_module_list_file', self._generate_module_list_file)()
    Task('convert_poms', self._convert_poms)()
    Task('regenerate_external_protos', self._regenerate_external_protos)()
    Task('regenerate_3rdparty', self._regenerate_3rdparty)()

def usage():
  print "usage: {0} [args] ".format(sys.argv[0])
  print "Regenerates the BUILD.* files for the repo"
  print ""
  print "-?,-h         Show this message"
  PomUtils.common_usage()

def main():
  arguments = PomUtils.parse_common_args(sys.argv[1:])
  flags = set(arg for arg in arguments if arg.startswith('-'))
  paths = list(set(arguments) - flags)
  paths = paths or [os.getcwd()]
  if len(paths) > 1:
    logger.error('Multiple repo root paths not supported.')
    return

  path = os.path.realpath(paths[0])

  for f in flags:
    if f == '-h' or f == '-?':
      usage()
      return
    else:
      print ("Unknown flag {0}".format(f))
      usage()
      return
  main_run = Task('main', lambda: RegenerateAll(path, flags).execute())
  main_run()
  logger.info('Regenerated BUILD files in {duration:0.3f} seconds.'
              .format(duration=main_run.duration))


if __name__ == '__main__':
  main()
