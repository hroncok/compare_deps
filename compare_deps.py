# This code is public domain
import dnf
import sys
from functools import partial


RAWHIDEVER = 35  # Fedora rawhide version
BRANCHEDVER = 34  # Fedora branched version

DNF_CACHEDIR = '_dnf_cache_dir'
ARCH = 'x86_64'

debug = partial(print, file=sys.stderr)


def sack(name, **kwargs):
    """A DNF sack for rawhide, used for queries, cached"""
    debug(f'Creating repoquery sack for {name}')
    base = dnf.Base()
    conf = base.conf
    conf.cachedir = DNF_CACHEDIR
    conf.substitutions['basearch'] = ARCH
    base.repos.add_new_repo(
        name,
        conf,
        **kwargs,
        skip_if_unavailable=False,
        enabled=True)
    base.fill_sack(load_system_repo=False, load_available_repos=True)
    return base.sack


SACKS = {
    # 'rawhide': sack('rawhide', metalink='https://mirrors.fedoraproject.org/metalink?repo=rawhide&arch=$basearch'),
    'rawhide': sack('rawhide', baseurl=['http://kojipkgs.fedoraproject.org/repos/rawhide/latest/$basearch/']),
    'copr': sack('copr', baseurl=['https://download.copr.fedorainfracloud.org/results/@python/python-distgen-importlib/fedora-rawhide-$basearch/']),
}


def repoquery(*args, **kwargs):
    """
    A Python function that somehow works as the repoquery.

    Returns a set of stings.
    """
    kwargs.setdefault('latest', 1)
    repo = kwargs.pop('repo')
    sack = SACKS[repo]

    deps = kwargs.pop('deps', None)

    pkgs = sack.query().filter(**kwargs).run()
    if deps:
        return {str(pkg) for pkg in getattr(pkgs[-1], deps)}
    return {str(pkg) for pkg in pkgs}


def same_dist(nevra1, nevra2):
    """Given two nevra strings, determine if they ~match"""
    nevra1 = nevra1.replace('-0:', '').replace(f'fc{BRANCHEDVER}', f'fc{RAWHIDEVER}')
    nevra2 = nevra2.replace('-0:', '').replace(f'fc{BRANCHEDVER}', f'fc{RAWHIDEVER}')
    return nevra1 == nevra2


def pkgname(nevra):
    """Given package nevra, return the name. Nevra must be valid."""
    return nevra.rsplit('-', 2)[0]


def pkgarch(nevra):
    """Given package nevra, return the arch string. Nevra must be valid."""
    return nevra.rpartition('.')[-1]


def filter_pythondist_deps(deps):
    """We only care for specific dependencies"""
    return {d for d in deps if d.startswith(('python3dist(', 'python3.9dist('))}


def report_different_deps(name, arch, rawhide_nevra, copr_nevra):
    """Report differences in requires and provides wrt python dist deps."""
    different = False

    for deps in 'requires', 'provides':
        rawhide_deps = repoquery(repo='rawhide', name=name, arch=arch, deps=deps)
        copr_deps = repoquery(repo='copr', name=name, arch=arch, deps=deps)

        rawhide_pydeps = filter_pythondist_deps(rawhide_deps)
        copr_pydeps = filter_pythondist_deps(copr_deps)

        if rawhide_pydeps != copr_pydeps:
            different = True
            extra_in_copr = copr_pydeps - rawhide_pydeps
            extra_in_rawhide = rawhide_pydeps - copr_pydeps
            if extra_in_copr:
                print(f'{name} has extra {deps} in copr:\n    {extra_in_copr}')
            if extra_in_rawhide:
                print(f'{name} has missing {deps} in copr:\n    {extra_in_rawhide}')

    if different:
        if not same_dist(rawhide_nevra, copr_nevra):
            debug(f'WARNING: {rawhide_nevra} != {copr_nevra}')
        print()


COPR_PACKAGES = repoquery(repo='copr')

for copr_nevra in COPR_PACKAGES:
    arch = pkgarch(copr_nevra)
    if arch == 'src':
        continue
    name = pkgname(copr_nevra)
    if name.endswith(('-debuginfo', '-debugsource')):
        continue
    rawhide_packages = repoquery(repo='rawhide', name=name, arch=arch)
    if rawhide_packages:
        rawhide_nevra = rawhide_packages.pop()
        report_different_deps(name, arch, rawhide_nevra, copr_nevra)
    else:
        debug(f'WARNING: {name} not found in rawhide\n')
