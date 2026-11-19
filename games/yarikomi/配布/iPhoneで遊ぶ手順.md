# iPhone で遊ぶ手順（Cloudflare Pages ＋ Cloudflare Access）

オーナーだけが開ける形で、ゲームを iPhone のブラウザで遊べるようにする手順です。
**置く操作・設定はオーナーが行います**（スタジオは公開の操作をしません）。

- 費用：Cloudflare Pages は無料で使えます。Cloudflare Zero Trust（Access）は、50人未満なら無料プランで使えます（[Cloudflare 公式：Zero Trust の料金](https://www.cloudflare.com/plans/zero-trust-services/)。料金は変わることがあるので、申し込みの前に公式ページで確かめてください）
- 画面のボタン名は変わることがあります。下の名前と違うときは、近い名前のものを選んでください
- 2026-11-19 時点で、公式の文書の検索結果から書いています。オーナーの画面ではまだ確かめていません。違っていたら教えてください、直します

## 用意するもの
- Cloudflare のアカウント（無料）
- 遊ぶ人のメールアドレス（オーナーのもの。ここにログインのコードが届きます）
- ゲームのファイル：このフォルダの `yarikomi_q1.zip`（GitHub の画面からダウンロード）

## 1. ゲームを置く（Cloudflare Pages の Direct Upload）
1. Cloudflare のダッシュボードで **Workers & Pages** を開く
2. **Create application** → **Pages** のほうの **Get started** → **Drag and drop your files**（または Upload assets）
3. プロジェクト名を入れる（例：`tsugite-kobo`。これが `tsugite-kobo.pages.dev` という住所になります。実在の名前やオーナーの名前は入れないのがおすすめ）
4. `yarikomi_q1.zip` をそのまま落とす → **Deploy site**
5. 出てきた `https://<プロジェクト名>.pages.dev` を PC で開き、ゲームのタイトルが出るか確かめる

出典：[Cloudflare Docs：Direct Upload](https://developers.cloudflare.com/pages/get-started/direct-upload/)
注意：Direct Upload で作ったプロジェクトは、あとから GitHub 連携には切り替えられません（必要になったら別のプロジェクトを作ります。同じ文書より）。

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
スタジオが新しい zip をこのフォルダに置いたら、Pages のプロジェクトで **Create deployment**（Create new deployment）→ 本番（Production）を選んで zip を落とす。Access の設定はそのまま効きます。
