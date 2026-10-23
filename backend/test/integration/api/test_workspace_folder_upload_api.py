from __future__ import annotations

from hashlib import sha256
from pathlib import PurePosixPath
from uuid import uuid4

import pytest

from yuxi.modules.workspace import paths as workspace_paths

pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.self_managed_resources]


async def _upload(test_client, headers, root: str, entries: list[tuple[str, bytes]], *, parent_path: str = "/"):
    """用真实 multipart 上传一组相对于当前目录的文件。"""
    return await test_client.post(
        "/api/workspace/upload",
        data={
            "parent_path": parent_path,
            "relative_paths": [f"{root}/{path}" for path, _content in entries],
        },
        files=[("files", (PurePosixPath(path).name, content, "application/octet-stream")) for path, content in entries],
        headers=headers,
    )


async def test_folder_upload_preserves_tree_bytes_and_merges_existing_directory(test_client, standard_user):
    """嵌套目录、跨目录同名文件和隐藏文件都按相对路径落盘。"""
    headers = standard_user["headers"]
    root = f"pytest-folder-{uuid4().hex}"
    entries = [
        ("a.txt", b"alpha"),
        ("sub/b.txt", b"beta"),
        ("sub/c.txt", b"gamma"),
        ("other/report.txt", b"other-report"),
        ("sub/report.txt", b"sub-report"),
        (".hidden.txt", b"hidden"),
    ]
    try:
        response = await _upload(test_client, headers, root, entries)
        assert response.status_code == 200, response.text
        assert {entry["path"] for entry in response.json()["entries"]} == {f"/{root}/{path}" for path, _content in entries}

        parent = await test_client.get("/api/workspace/tree", headers=headers)
        assert parent.status_code == 200, parent.text
        uploaded_root = next(entry for entry in parent.json()["entries"] if entry["name"] == root)
        assert uploaded_root["is_dir"] is True
        assert uploaded_root["path"] == f"/{root}/"
        assert not {entry["name"] for entry in parent.json()["entries"]} & {"a.txt", "report.txt", ".hidden.txt"}

        tree = await test_client.get("/api/workspace/tree", params={"path": f"/{root}", "recursive": True}, headers=headers)
        assert tree.status_code == 200, tree.text
        paths = {entry["path"] for entry in tree.json()["entries"]}
        assert {f"/{root}/{path}" for path, _content in entries} <= paths
        assert {f"/{root}/sub/", f"/{root}/other/"} <= paths

        for path, content in entries:
            downloaded = await test_client.get("/api/workspace/download", params={"path": f"/{root}/{path}"}, headers=headers)
            assert downloaded.status_code == 200, downloaded.text
            assert sha256(downloaded.content).hexdigest() == sha256(content).hexdigest()

        merged = await _upload(test_client, headers, root, [("sub/d.txt", b"delta")])
        assert merged.status_code == 200, merged.text
        assert merged.json()["entries"][0]["path"] == f"/{root}/sub/d.txt"
        workspace = workspace_paths.user_workspace_dir(str(standard_user["user"]["uid"]))
        assert (workspace / root / "sub" / "d.txt").read_bytes() == b"delta"
    finally:
        removed = await test_client.delete("/api/workspace/file", params={"path": f"/{root}"}, headers=headers)
        assert removed.status_code in {200, 404}, removed.text


async def test_folder_upload_preserves_one_root_across_batches(test_client, standard_user):
    """超过单请求数量的文件跨批仍属于同一根目录。"""
    headers = standard_user["headers"]
    root = f"pytest-batches-{uuid4().hex}"
    entries = [(f"sub-{index}/same.txt", f"content-{index}".encode()) for index in range(51)]
    try:
        for batch in [entries[:50], entries[50:]]:
            response = await _upload(test_client, headers, root, batch)
            assert response.status_code == 200, response.text

        parent = await test_client.get("/api/workspace/tree", headers=headers)
        assert parent.status_code == 200, parent.text
        assert [entry["path"] for entry in parent.json()["entries"] if entry["name"] == root] == [f"/{root}/"]
        workspace = workspace_paths.user_workspace_dir(str(standard_user["user"]["uid"]))
        assert not (workspace / "same.txt").exists()
        assert sorted(str(path.relative_to(workspace / root)) for path in (workspace / root).rglob("*") if path.is_file()) == sorted(
            path for path, _content in entries
        )
        for path, content in entries:
            assert (workspace / root / path).read_bytes() == content
    finally:
        removed = await test_client.delete("/api/workspace/file", params={"path": f"/{root}"}, headers=headers)
        assert removed.status_code in {200, 404}, removed.text


@pytest.mark.parametrize("root", [" 前导空白目录", "中文目录"])
async def test_folder_upload_preserves_root_name(test_client, standard_user, root):
    """合法目录名原样写入且能从目录树继续浏览。"""
    headers = standard_user["headers"]
    try:
        response = await _upload(test_client, headers, root, [("sub/a.txt", b"alpha")])
        assert response.status_code == 200, response.text
        assert response.json()["entries"][0]["path"] == f"/{root}/sub/a.txt"
        tree = await test_client.get("/api/workspace/tree", params={"path": f"/{root}"}, headers=headers)
        assert tree.status_code == 200, tree.text
        assert [entry["path"] for entry in tree.json()["entries"]] == [f"/{root}/sub/"]
        downloaded = await test_client.get("/api/workspace/download", params={"path": f"/{root}/sub/a.txt"}, headers=headers)
        assert downloaded.status_code == 200, downloaded.text
        assert downloaded.content == b"alpha"
    finally:
        removed = await test_client.delete("/api/workspace/file", params={"path": f"/{root}"}, headers=headers)
        assert removed.status_code in {200, 404}, removed.text


@pytest.mark.parametrize("path", ["root/a.txt ", "root /a.txt", "root/sub\t/a.txt"])
async def test_folder_upload_rejects_unaddressable_names(test_client, standard_user, path):
    """尾随空白不能被静默裁掉，也不能留下无法浏览的目录。"""
    response = await test_client.post(
        "/api/workspace/upload",
        data={"parent_path": "/", "relative_paths": [path]},
        files=[("files", ("a.txt", b"alpha"))],
        headers=standard_user["headers"],
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"] == {"code": "workspace_upload_path_invalid", "message": "路径组件不能以空白字符结尾"}
    workspace = workspace_paths.user_workspace_dir(str(standard_user["user"]["uid"]))
    assert not (workspace / "root").exists()
    assert not (workspace / "root ").exists()


@pytest.mark.parametrize("paths", [["node", "node/child.txt"], ["node/child.txt", "node"]])
async def test_folder_upload_rejects_ancestor_targets_before_creating_directories(test_client, standard_user, paths):
    """同批祖先冲突必须在写入前拒绝，不能留下半批目录。"""
    root = f"pytest-prefix-{uuid4().hex}"
    response = await _upload(test_client, standard_user["headers"], root, [(path, b"x") for path in paths])
    assert response.status_code == 400, response.text
    assert response.json()["detail"]["code"] == "workspace_upload_path_conflict"
    workspace = workspace_paths.user_workspace_dir(str(standard_user["user"]["uid"]))
    assert not (workspace / root).exists()


@pytest.mark.parametrize(
    "relative_path",
    [
        "../outside.txt",
        "/absolute.txt",
        r"root\evil.txt",
        "root//empty-segment.txt",
        "root/./dot.txt",
        "root/../parent.txt",
        "root/",
        "",
        "C:/drive.txt",
        "root/\x00nul.txt",
        "/".join(["a"] * 65) + "/x.txt",
        "a" * 300 + "/x.txt",
        "/".join(["b" * 64] * 63) + "/x.txt",
    ],
)
async def test_folder_upload_rejects_invalid_relative_paths(test_client, standard_user, relative_path: str):
    """非法相对路径在真实 HTTP 边界被拒绝且不产生越界文件。"""
    headers = standard_user["headers"]

    response = await test_client.post(
        "/api/workspace/upload",
        data={"parent_path": "/", "relative_paths": [relative_path]},
        files=[("files", ("x.txt", b"x", "application/octet-stream"))],
        headers=headers,
    )

    assert response.status_code == 422, response.text
    workspace = workspace_paths.user_workspace_dir(str(standard_user["user"]["uid"]))
    assert not (workspace.parent / "outside.txt").exists()
    assert not (workspace / "x.txt").exists()
    assert not (workspace / "root").exists()
    assert not (workspace / "a").exists()
    assert not (workspace / ("b" * 64)).exists()


async def test_flat_upload_rejects_overlong_filename_without_500(test_client, standard_user):
    """普通上传的超长文件名也走同一预检映射，不能退化为 500。"""
    headers = standard_user["headers"]
    filename = "a" * 300 + ".txt"

    response = await test_client.post(
        "/api/workspace/upload",
        data={"parent_path": "/"},
        files={"files": (filename, b"x", "application/octet-stream")},
        headers=headers,
    )

    assert response.status_code == 422, response.text
    assert "文件路径过长" in response.text
    workspace = workspace_paths.user_workspace_dir(str(standard_user["user"]["uid"]))
    assert not any(entry.name.startswith("a" * 300) for entry in workspace.iterdir())


async def test_folder_upload_rejects_existing_file_before_writing_other_targets(test_client, standard_user):
    """目标冲突在写入前发现，不能留下本批其他文件。"""
    headers = standard_user["headers"]
    root = f"pytest-conflict-{uuid4().hex}"
    try:
        first = await _upload(test_client, headers, root, [("a.txt", b"original")])
        assert first.status_code == 200, first.text

        conflict = await _upload(test_client, headers, root, [("new.txt", b"new"), ("a.txt", b"replacement")])
        assert conflict.status_code == 400, conflict.text
        assert "已存在" in conflict.text

        downloaded = await test_client.get("/api/workspace/download", params={"path": f"/{root}/a.txt"}, headers=headers)
        assert downloaded.status_code == 200, downloaded.text
        assert downloaded.content == b"original"
        missing = await test_client.get("/api/workspace/download", params={"path": f"/{root}/new.txt"}, headers=headers)
        assert missing.status_code == 404, missing.text
    finally:
        await test_client.delete("/api/workspace/file", params={"path": f"/{root}"}, headers=headers)


async def test_folder_upload_rejects_file_directory_conflict_with_4xx(test_client, standard_user):
    """目录位置已有普通文件时返回业务错误，且不破坏原文件。"""
    headers = standard_user["headers"]
    root = f"pytest-type-conflict-{uuid4().hex}"
    try:
        first = await _upload(test_client, headers, root, [("block", b"file-content")])
        assert first.status_code == 200, first.text

        conflict = await _upload(test_client, headers, root, [("block/child.txt", b"child")])
        assert conflict.status_code == 400, conflict.text
        assert "目标路径不可用" in conflict.text

        downloaded = await test_client.get("/api/workspace/download", params={"path": f"/{root}/block"}, headers=headers)
        assert downloaded.status_code == 200, downloaded.text
        assert downloaded.content == b"file-content"
    finally:
        await test_client.delete("/api/workspace/file", params={"path": f"/{root}"}, headers=headers)


async def test_folder_upload_uses_non_root_parent_path(test_client, standard_user):
    """相对路径解析必须叠加在当前目录而不是工作区根。"""
    headers = standard_user["headers"]
    parent = f"pytest-parent-{uuid4().hex}"
    root = f"pytest-nested-{uuid4().hex}"
    created = await test_client.post("/api/workspace/directory", json={"parent_path": "/", "name": parent}, headers=headers)
    assert created.status_code == 200, created.text
    try:
        response = await _upload(test_client, headers, root, [("a.txt", b"alpha")], parent_path=f"/{parent}")
        assert response.status_code == 200, response.text
        assert response.json()["entries"][0]["path"] == f"/{parent}/{root}/a.txt"

        downloaded = await test_client.get("/api/workspace/download", params={"path": f"/{parent}/{root}/a.txt"}, headers=headers)
        assert downloaded.status_code == 200, downloaded.text
        assert downloaded.content == b"alpha"
    finally:
        await test_client.delete("/api/workspace/file", params={"path": f"/{parent}"}, headers=headers)


async def test_folder_upload_rejects_existing_directory_target(test_client, standard_user):
    """目标路径已是目录时按同名冲突返回 4xx，不覆盖其内容。"""
    headers = standard_user["headers"]
    root = f"pytest-dir-target-{uuid4().hex}"
    try:
        first = await _upload(test_client, headers, root, [("block/a.txt", b"a")])
        assert first.status_code == 200, first.text

        conflict = await _upload(test_client, headers, root, [("block", b"file")])
        assert conflict.status_code == 400, conflict.text
        assert "已存在" in conflict.text

        downloaded = await test_client.get("/api/workspace/download", params={"path": f"/{root}/block/a.txt"}, headers=headers)
        assert downloaded.status_code == 200, downloaded.text
        assert downloaded.content == b"a"
    finally:
        await test_client.delete("/api/workspace/file", params={"path": f"/{root}"}, headers=headers)


async def test_folder_upload_rejects_parent_depth_accumulation(test_client, standard_user):
    """parent_path 的累积深度也计入上限，不能借既有深目录继续加深。"""
    headers = standard_user["headers"]
    uid = str(standard_user["user"]["uid"])
    workspace_paths.ensure_user_workspace(uid)
    workspace = workspace_paths.user_workspace_dir(uid)
    accepted_parent = "/".join(["q"] * 62)
    (workspace / accepted_parent).mkdir(parents=True)
    parent = "/".join(["p"] * 63)
    (workspace / parent).mkdir(parents=True)
    try:
        accepted = await _upload(test_client, headers, "root", [("b.txt", b"b")], parent_path=f"/{accepted_parent}")
        assert accepted.status_code == 200, accepted.text
        assert (workspace / accepted_parent / "root/b.txt").read_bytes() == b"b"

        relative = await _upload(test_client, headers, "root", [("b.txt", b"b")], parent_path=f"/{parent}")
        assert relative.status_code == 422, relative.text
        assert not (workspace / parent / "root").exists()

        deeper = f"{parent}/p"
        (workspace / deeper).mkdir()
        direct = await _upload(test_client, headers, "root", [("x.txt", b"x")], parent_path=f"/{deeper}")
        assert direct.status_code == 422, direct.text
        assert not (workspace / deeper / "root").exists()
    finally:
        removed_p = await test_client.delete("/api/workspace/file", params={"path": "/p"}, headers=headers)
        assert removed_p.status_code in {200, 404}, removed_p.text
        removed_q = await test_client.delete("/api/workspace/file", params={"path": "/q"}, headers=headers)
        assert removed_q.status_code in {200, 404}, removed_q.text


async def test_folder_upload_rejects_symlink_parent_without_writing_outside(test_client, standard_user):
    """工作区内符号链接不能成为上传父目录。"""
    headers = standard_user["headers"]
    uid = str(standard_user["user"]["uid"])
    workspace_paths.ensure_user_workspace(uid)
    workspace = workspace_paths.user_workspace_dir(uid)
    outside = workspace.parent / f"pytest-outside-{uuid4().hex}"
    outside.mkdir()
    link = workspace / f"pytest-link-{uuid4().hex}"
    link.symlink_to(outside, target_is_directory=True)
    try:
        response = await test_client.post(
            "/api/workspace/upload",
            data={"parent_path": "/", "relative_paths": [f"{link.name}/evil.txt"]},
            files=[("files", ("evil.txt", b"evil", "application/octet-stream"))],
            headers=headers,
        )

        assert response.status_code == 400, response.text
        assert not (outside / "evil.txt").exists()
    finally:
        link.unlink(missing_ok=True)
        outside.rmdir()


async def test_folder_upload_rejects_duplicate_targets_count_mismatch_and_over_limit(test_client, standard_user):
    """重复目标、路径数量不一致和超过数量上限都在写入前拒绝。"""
    headers = standard_user["headers"]
    root = f"pytest-limits-{uuid4().hex}"

    duplicate = await test_client.post(
        "/api/workspace/upload",
        data={"parent_path": "/", "relative_paths": [f"{root}/a.txt", f"{root}/a.txt"]},
        files=[("files", ("a.txt", b"first")), ("files", ("a.txt", b"second"))],
        headers=headers,
    )
    assert duplicate.status_code == 400, duplicate.text
    assert "上传目标重复" in duplicate.text

    mismatch = await test_client.post(
        "/api/workspace/upload",
        data={"parent_path": "/", "relative_paths": [f"{root}/a.txt"]},
        files=[("files", ("a.txt", b"a")), ("files", ("b.txt", b"b"))],
        headers=headers,
    )
    assert mismatch.status_code == 422, mismatch.text
    assert "相对路径数量" in mismatch.text

    names = [f"f-{index}.txt" for index in range(51)]
    over_limit = await test_client.post(
        "/api/workspace/upload",
        data={"parent_path": "/", "relative_paths": [f"{root}/{name}" for name in names]},
        files=[("files", (name, b"x")) for name in names],
        headers=headers,
    )
    assert over_limit.status_code == 400, over_limit.text
    assert "一次最多上传" in over_limit.text
    workspace = workspace_paths.user_workspace_dir(str(standard_user["user"]["uid"]))
    assert not (workspace / root).exists()
