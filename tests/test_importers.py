from ponkan.importers import google_sheet_csv_url, parse_csv


def test_google_sheet_share_url_is_normalized():
    url = "https://docs.google.com/spreadsheets/d/abc123/edit?gid=42#gid=42"
    assert google_sheet_csv_url(url) == (
        "https://docs.google.com/spreadsheets/d/abc123/export?format=csv&gid=42"
    )


def test_generic_schema():
    rows = parse_csv(
        "id,prompt,answer,choices,tags,prompt_lang,answer_lang\n"
        "q1,你好,こんにちは,こんにちは|こんばんは,chinese|hsk,zh-CN,ja\n"
    )
    assert len(rows) == 1
    assert rows[0].prompt == "你好"
    assert rows[0].choices == ["こんにちは", "こんばんは"]
    assert rows[0].tags == ["chinese", "hsk"]


def test_legacy_word_meaning_schema():
    rows = parse_csv("id,word,meaning,tags\n1,abandon,放棄する,english\n", "en", "ja")
    assert rows[0].prompt == "abandon"
    assert rows[0].answer == "放棄する"
    assert rows[0].prompt_lang == "en"
