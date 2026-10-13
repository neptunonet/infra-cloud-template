#!/usr/bin/env bash
# Prints the image references that a pipeline run must push, one per line.
#
#   compute-tags.sh <image> <git-sha> <git-ref>
#
# Rules (the whole versioning policy of the class in 15 lines):
#   - every run          -> <image>:<git-sha>         (traceable to one commit)
#   - ref is a tag vX.Y.Z -> also <image>:vX.Y.Z      (human-friendly release)
#   - anything else that looks like a tag (v1, vfoo) is rejected on purpose.
# There is NO ":latest": a moving tag is not a version.
set -euo pipefail

if [ "$#" -ne 3 ]; then
  echo "usage: $0 <image> <git-sha> <git-ref>" >&2
  exit 2
fi
image="$1"
sha="$2"
ref="$3"

if ! [[ "$sha" =~ ^[0-9a-f]{7,40}$ ]]; then
  echo "invalid sha: $sha" >&2
  exit 2
fi

echo "${image}:${sha}"

case "$ref" in
  refs/tags/*)
    tag="${ref#refs/tags/}"
    if [[ "$tag" =~ ^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]; then
      echo "${image}:${tag}"
    else
      echo "tag '$tag' is not semver (vMAJOR.MINOR.PATCH)" >&2
      exit 1
    fi
    ;;
esac
