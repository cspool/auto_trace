"""Factor repeated authorization-map construction out of outer prefix checks.

Every unique directory binding, each used file binding and final resolved path
are still checked live on every call. Byte hashing remains the caller's job.
"""
from pathlib import Path
import os


class OuterSourcePathValidator:
    def __init__(self, common):
        self.common = common
        self.directories = common.directory_mappings()
        self.files, _ = common.storage_mappings()
        self.normalized = {}
        self.mapping_directory_bindings = set()
        for source, record in self.files.items():
            target, bindings = self._rebind(source)
            common.check(target not in self.normalized, 'unambiguous normalized file map')
            self.normalized[target] = record
            self.mapping_directory_bindings.update(bindings)

    def _rebind(self, path):
        seen = set()
        bindings = set()
        while True:
            self.common.check(path not in seen, 'no directory relocation cycle')
            seen.add(path)
            for lexical, destination in self.directories.items():
                if path.is_relative_to(lexical):
                    bindings.add((lexical, destination))
                    path = destination / path.relative_to(lexical)
                    break
            else:
                return path, bindings

    def validate_path(self, value):
        c = self.common
        source = c.localize(value)
        rebound, source_bindings = self._rebind(source)
        # The old implementation checked the same bindings once per mapped
        # source. Preserve all those checks, once per distinct binding per call.
        for lexical, destination in self.mapping_directory_bindings | source_bindings:
            c.check(lexical.is_symlink() and os.readlink(lexical) == str(destination),
                    'exact authorized directory symlink')
        c.check(source.is_relative_to(c.PROJECT) or source.is_relative_to(c.CONTROL)
                or source in self.files
                or any(source.is_relative_to(p) for p in self.directories.values()),
                'explicit source owner')
        seen = set()
        while rebound in self.normalized:
            c.check(rebound not in seen, 'no storage relocation cycle')
            seen.add(rebound)
            item = self.normalized[rebound]
            destination = Path(item['destination_path'])
            c.check(rebound.is_symlink() and os.readlink(rebound) == str(destination),
                    'exact authorized file symlink')
            c.check(rebound.stat().st_size == item['size'], 'relocated file size')
            rebound = destination
        c.check(source.resolve() == rebound and not rebound.is_symlink(),
                'no unlisted path or nested symlink')
        return source
