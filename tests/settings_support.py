import yaml

from beeagent_module.core.paths import get_project_root
from beeagent_module.core.settings import validate_settings


def read_test_settings() -> dict:
    settings = yaml.safe_load(
        (get_project_root() / "config/settings.yml").read_text(encoding="utf-8")
    )
    assert isinstance(settings, dict)
    for module in settings["modules"]["registry"]:
        module["enabled"] = module["id"] == "beescan"
    settings["ai"]["default_profile"] = "openai"
    for profile in settings["ai"]["profiles"].values():
        profile.pop("enabled", None)
    beescan = settings["beescan"]
    for key in beescan:
        if key.endswith("_enabled"):
            beescan[key] = False
        elif key == "approval" or key.endswith("_approval"):
            beescan[key] = None
    beescan["investigation"].update(
        enabled=False,
        trusted_local_enabled=False,
        local_lab_enabled=False,
        approval=None,
        ai_profile="openrouter",
    )
    settings["beedrill"]["ai_assist"].update(enabled=False)
    settings["beedrill"]["ai_assist"].pop("ai_profile", None)
    rop = settings["rop"]
    rop["ai_assist"].update(enabled=True, dry_run=False)
    rop["ai_assist"].pop("ai_profile", None)
    rop["ai_assist"]["adjudicator"]["enabled"] = True
    rop["mailbox_poll"].update(enabled=True, sources_all=True)
    rop["attachments"]["enabled"] = True
    rop["attachments"]["storage"]["enabled"] = True
    settings["web"]["auth"]["enabled"] = True
    bitrix = settings["bitrix"]
    bitrix["enabled"] = True
    bitrix["widget"]["enabled"] = False
    bitrix["embedded_app"].update(enabled=True, portal_origin="https://portal.test")
    bitrix["writeback"].update(enabled=True, dry_run=False)
    bitrix["reconciliation"]["enabled"] = True
    bitrix["blacklist_trigger"]["enabled"] = True
    return settings


def load_test_settings() -> dict:
    settings = read_test_settings()
    validate_settings(settings, project_root=get_project_root())
    return settings
