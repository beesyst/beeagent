from dataclasses import replace
from inspect import unwrap

import pytest

from beeagent_module.integrations.beescan import providers as native
from beeagent_module.integrations.beescan.policy import HTTPX_SHA256, ProbePolicy
from integration_tests import test_beescan_assessment_lab as real_lab
from tests import test_beescan_detection, test_beescan_providers

approved = test_beescan_detection.approved
distribution = test_beescan_providers.distribution


@pytest.fixture
def bootstrap_lab(distribution, approved, monkeypatch):
    root, _, content, _ = distribution
    detection, _, storage = approved
    httpx = root.parent / "httpx"
    httpx.write_bytes(content)
    httpx.chmod(0o555)
    fields = {
        name: getattr(detection, name) for name in ProbePolicy.__dataclass_fields__
    }
    fields.update(
        method="http_probe",
        sha256=HTTPX_SHA256,
        provider_version="1.12.0",
        executable=str(httpx),
    )
    probe = ProbePolicy(**fields)
    monkeypatch.setenv("BEEAGENT_BEESCAN_NUCLEI", str(root / "nuclei"))

    def prepare(policy=probe):
        fixture = unwrap(real_lab.assessment_lab)
        return fixture((policy, storage), approved)

    return root, probe, prepare


def test_assessment_lab_bootstraps_managed_nuclei_and_reuses_offline(
    bootstrap_lab, distribution, monkeypatch
):
    root, probe, prepare = bootstrap_lab
    _, _, content, _ = distribution
    settings, returned_probe, _ = prepare()
    assert returned_probe is probe
    assert settings["beescan"]["detection_approval"]["executable"] == str(
        root / "nuclei"
    )
    assert settings["beescan"]["approval"]["executable"] == probe.executable
    binary = root / "nuclei"
    assert binary.read_bytes() == content
    before = binary.stat()
    monkeypatch.setattr(
        native, "_download", lambda *_: pytest.fail("download forbidden")
    )
    prepare()
    assert binary.stat() == before


@pytest.mark.parametrize("failure", ["custom_missing", "download", "corrupt", "httpx"])
def test_assessment_lab_bootstrap_fails_explicitly(bootstrap_lab, monkeypatch, failure):
    root, probe, prepare = bootstrap_lab
    if failure == "custom_missing":
        custom = root.parent / "missing-nuclei"
        monkeypatch.setenv("BEEAGENT_BEESCAN_NUCLEI", str(custom))
        message = "Custom provider path is missing"
    elif failure == "download":

        def unavailable(*_):
            raise OSError("download unavailable")

        monkeypatch.setattr(native, "_download", unavailable)
        message = "Cannot safely provision"
    elif failure == "corrupt":
        prepare()
        binary = root / "nuclei"
        binary.chmod(0o755)
        binary.write_bytes(b"corrupt")
        message = "integrity or permissions mismatch"
    else:
        probe = replace(probe, executable=str(root.parent / "missing-httpx"))
        message = "Pinned httpx distribution unavailable"
    if failure != "download":
        monkeypatch.setattr(
            native, "_download", lambda *_: pytest.fail("download forbidden")
        )
    with pytest.raises(native.ProviderProvisioningError, match=message):
        prepare(probe)
    if failure == "corrupt":
        assert (root / "nuclei").read_bytes() == b"corrupt"
    else:
        assert not (root / "nuclei").exists()
    assert not (root.parent / "missing-nuclei").exists()
    assert not (root.parent / "missing-httpx").exists()


@pytest.mark.parametrize("mode", [0o644, 0o664, 0o666])
def test_git_lab_requires_protected_installed_signature(tmp_path, monkeypatch, mode):
    from beescan.domain import git_head_signature

    asset = tmp_path / "git_head_signature.py"
    asset.write_bytes(b"# installed signature fixture\n")
    asset.chmod(mode)
    monkeypatch.setattr(git_head_signature, "__file__", str(asset))
    before = asset.stat()
    if mode == 0o644:
        real_lab.check_git_signature_asset()
    else:
        with pytest.raises(pytest.fail.Exception, match="umask 022"):
            real_lab.check_git_signature_asset()
    assert asset.stat() == before
