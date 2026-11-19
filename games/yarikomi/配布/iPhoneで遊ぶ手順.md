# iPhone で遊ぶ手順（Cloudflare Pages の GitHub 連携 ＋ Cloudflare Access）

オーナーだけが開ける形で、ゲームを iPhone のブラウザで遊べるようにする手順です。
**置く操作・設定はオーナーが行います**（スタジオは公開の操作をしません）。

- 費用：Cloudflare Pages は無料で使えます。Cloudflare Zero Trust（Access）は、50人未満なら無料プランで使えます（[Cloudflare 公式：Zero Trust の料金](https://www.cloudflare.com/plans/zero-trust-services/)。料金は変わることがあるので、申し込みの前に公式ページで確かめてください）
- 画面のボタン名は変わることがあります。下の名前と違うときは、近い名前のものを選んでください
- 2026-11-19 時点で、公式の文書の検索結果から書いています。オーナーの画面ではまだ確かめていません。違っていたら教えてください、直します

## 用意するもの
- Cloudflare のアカウント（無料）
- 遊ぶ人のメールアドレス（オーナーのもの。ここにログインのコードが届きます）
- スマホだけでできます（ファイルを置く操作はありません。Cloudflare が GitHub のこのリポジトリから直接ゲームを取りに行きます）

ゲームのファイルは、リポジトリの `games/yarikomi/public/` にスタジオが置きます（英数字だけのフォルダ）。スタジオが新しい版をプッシュすると、自動で入れ替わります。

## 1. ゲームを置く（Cloudflare Pages の GitHub 連携）
1. Cloudflare のダッシュボードで **Workers & Pages** を開く
2. **Create application** → **Pages** のほうを選ぶ → **Connect to Git**（Import an existing Git repository）
3. GitHub を選び、Cloudflare に GitHub を使う許可を出す。読ませるリポジトリは **このリポジトリだけ**（Only select repositories で `practice`）を選ぶのがおすすめ
4. リポジトリ `practice` を選んで次へ
5. 設定を入れる
   - Project name：例 `tsugite-kobo`（これが `tsugite-kobo.pages.dev` という住所になります。実在の名前やオーナーの名前は入れないのがおすすめ）
   - Production branch：`claude/friendly-galileo-eof9nq`
   - Framework preset：**None**
   - Build command：**空のまま**
   - Build output directory：`games/yarikomi/public`
6. **Save and Deploy** を押し、終わるまで待つ
7. 出てきた `https://<プロジェクト名>.pages.dev` を開き、ゲームのタイトルが出るか確かめる（ここで開けたら、すぐに 2. へ進んでください）
8. 余計な確認用の公開を減らすため、プロジェクトの **Settings** → **Builds**（または Builds & deployments）→ **Branch control** で、Preview branch を **None** にして保存する（本番のブランチだけが公開されます）

出典：[Cloudflare Docs：はじめての Pages（Git 連携）](https://developers.cloudflare.com/pages/get-started/guide/)、[Cloudflare Docs：GitHub integration](https://developers.cloudflare.com/pages/configuration/git-integration/github-integration/)、[Cloudflare Docs：Branch build controls](https://developers.cloudflare.com/pages/platform/branch-build-controls/)
注意：GitHub 連携で作ったプロジェクトは、あとから Direct Upload（zip を置く形）には切り替えられません（同じ文書より）。PC から zip を置く形にしたくなったら、別のプロジェクトを作ります（zip は `yarikomi_q1.zip` に残してあります）。

## 2. オーナーだけが開けるようにする（Cloudflare Access）
**この手順を終えるまで、住所を誰にも教えないでください**（終えるまでは誰でも開けます）。

1. Pages のプロジェクトで **Settings** → **General** → **Enable access policy** を押す。これで、更新のたびにできる確認用の住所（`xxxx.<プロジェクト名>.pages.dev`）が守られます
2. 本番の住所（`<プロジェクト名>.pages.dev`）も守るため、Cloudflare **Zero Trust** のダッシュボードを開く（初めてなら、チーム名を決めて **Free** プランを選ぶ）
3. **Access** → **Applications**（または Access controls → Applications）→ 1. で作られたアプリを開くか、**Add an application** → **Self-hosted** で新しく作る
4. 守る住所（Application domain / Public hostname）に、次の2つを入れる
   - `<プロジェクト名>.pages.dev`
   - `*.<プロジェクト名>.pages.dev`
5. 決まり（Policy）：**Action = Allow**、**Include = Emails** に遊ぶ人のメールアドレスだけを入れる
6. ログインの方法に **One-time PIN** が入っているか確かめる（**Settings → Authentication → Login methods**。なければ Add で足す）
7. 保存する

出典：[Cloudflare Docs：Pages の既知の問題（pages.dev とプレビューを守る）](https://developers.cloudflare.com/pages/platform/known-issues/)、[Cloudflare Docs：Preview deployments](https://developers.cloudflare.com/pages/configuration/preview-deployments/)、[Cloudflare Docs：One-time PIN](https://developers.cloudflare.com/cloudflare-one/identity/one-time-pin/)

## 3. 守れているか確かめる
1. スマホの**プライベートブラウズ**で `https://<プロジェクト名>.pages.dev` を開く → ゲームでなく、Cloudflare のログイン画面（メールアドレスを入れる画面）が出れば守れています
2. 自分のメールアドレスを入れる → 届いたコードを入れる → ゲームが開く
   - コードのメールは迷惑メールやプロモーションのフォルダに入ることがあります
3. 別のメールアドレスを入れても、コードが届かない（または入れない）ことを確かめる
4. 確認用の住所（Pages のプロジェクトの Deployments に出る `xxxx.<プロジェクト名>.pages.dev`）も、同じようにログイン画面になるか確かめる

## 4. iPhone で遊ぶ
1. iPhone の Safari で `https://<プロジェクト名>.pages.dev` を開き、コードでログイン
2. 共有ボタン → **ホーム画面に追加** すると、アプリのように開けます（保存が消えにくくなるとされています。技術選定 R1）
3. 遊んだら、メニュー →「記録」を開き、**書き出し**の文字をコピーしてスタジオ（このチャット）に貼ってください。解けるまでの時間・置き間違い・試した回数を見ます

## 5. 新しい版に入れ替えるとき
スタジオが `games/yarikomi/public/` を新しい版にしてプッシュすると、Cloudflare が自動で入れ替えます。オーナーの操作は要りません。Access の設定もそのまま効きます。
