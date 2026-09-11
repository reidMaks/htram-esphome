from unittest.mock import MagicMock, patch

from tools.device import HtramClient, load_credentials, resolve_device_address


def test_resolve_device_address():
    assert resolve_device_address("office") == "192.168.0.78"
    assert resolve_device_address("кабінет") == "192.168.0.78"
    assert resolve_device_address("bedroom") == "192.168.0.159"
    assert resolve_device_address("спальня") == "192.168.0.159"
    assert resolve_device_address("living") == "192.168.0.185"
    assert resolve_device_address("вітальня") == "192.168.0.185"
    assert resolve_device_address("c1da24") == "192.168.0.185"
    assert resolve_device_address("10.0.0.42") == "10.0.0.42"


def test_load_credentials():
    u, p = load_credentials()
    assert len(u) > 0
    assert len(p) > 0


@patch("requests.post")
def test_htram_client_press(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_post.return_value = mock_resp

    client = HtramClient("192.168.0.185")
    client.trigger_silence()

    assert mock_post.called
    args, kwargs = mock_post.call_args
    assert "%D0%A5%D0%B2%D0%B8%D0%BB%D0%B8%D0%BD%D0%B0" in args[0]
    assert kwargs.get("headers", {}).get("Content-Length") == "0"


@patch("requests.post")
def test_htram_client_reboot_and_beep(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_post.return_value = mock_resp

    client = HtramClient("office")
    client.beep()
    assert "button/Beep/press" in mock_post.call_args[0][0]

    client.reboot()
    assert "reboot" in mock_post.call_args[0][0]
