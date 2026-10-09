from flask import Flask, render_template, request, redirect, session, url_for
import sqlite3

app = Flask(__name__)
app.secret_key = "blogging_platform_secret_key"


# ---------------- DATABASE ----------------

def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():

    conn = get_db()
    cursor = conn.cursor()

    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
    """)

    # Posts table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    # Likes table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS likes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            post_id INTEGER NOT NULL,
            UNIQUE(user_id, post_id)
        )
    """)

    # Comments table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            post_id INTEGER NOT NULL,
            comment TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Followers table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS followers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            follower_id INTEGER NOT NULL,
            following_id INTEGER NOT NULL,
            UNIQUE(follower_id, following_id)
        )
    """)

    conn.commit()
    conn.close()


# ---------------- HOME ----------------


@app.route("/")
def home():
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()
    search_query = request.args.get("q", "").strip()

    posts = conn.execute("""
        SELECT
            p.id,
            p.user_id,
            p.title,
            p.content,
            p.created_at,
            u.username,
            (SELECT COUNT(*) FROM likes l
             WHERE l.post_id = p.id) AS like_count,
            (SELECT COUNT(*) FROM comments c
             WHERE c.post_id = p.id) AS comment_count,
            EXISTS(
                SELECT 1 FROM likes l
                WHERE l.post_id = p.id
                AND l.user_id = ?
            ) AS liked
        FROM posts p
        JOIN users u ON p.user_id = u.id
        WHERE p.title LIKE ? OR p.content LIKE ?
        ORDER BY p.created_at DESC
    """, (
        session["user_id"],
        f"%{search_query}%",
        f"%{search_query}%"
    )).fetchall()

    trending = conn.execute("""
        SELECT p.id, p.title, u.username,
               COUNT(l.id) AS likes
        FROM posts p
        JOIN users u ON p.user_id = u.id
        LEFT JOIN likes l ON l.post_id = p.id
        GROUP BY p.id
        ORDER BY likes DESC, p.created_at DESC
        LIMIT 3
    """).fetchall()

    suggested_users = conn.execute("""
        SELECT
            u.id,
            u.username,
            EXISTS(
                SELECT 1 FROM followers f
                WHERE f.follower_id = ?
                AND f.following_id = u.id
            ) AS is_following
        FROM users u
        WHERE u.id != ?
        ORDER BY u.username
        LIMIT 5
    """, (
        session["user_id"],
        session["user_id"]
    )).fetchall()

    conn.close()

    return render_template(
        "index.html",
        posts=posts,
        username=session["username"],
        search_query=search_query,
        trending=trending,
        suggested_users=suggested_users
    )

# ---------------- LOGIN ----------------

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        conn = get_db()

        user = conn.execute("""
            SELECT *
            FROM users
            WHERE email = ? AND password = ?
        """, (email, password)).fetchone()

        conn.close()

        if user:

            session["user_id"] = user["id"]
            session["username"] = user["username"]

            return redirect("/")

        return render_template(
            "login.html",
            error="Invalid email or password!"
        )

    return render_template("login.html")


# ---------------- LOGOUT ----------------

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/login")


# ---------------- CREATE POST ----------------

@app.route("/create_post", methods=["GET", "POST"])
def create_post():

    if "user_id" not in session:
        return redirect("/login")

    if request.method == "POST":

        title = request.form["title"]
        content = request.form["content"]

        conn = get_db()

        conn.execute("""
            INSERT INTO posts (user_id, title, content)
            VALUES (?, ?, ?)
        """, (
            session["user_id"],
            title,
            content
        ))

        conn.commit()
        conn.close()

        return redirect("/")

    return render_template("create_post.html")


# ---------------- EDIT POST ----------------

@app.route("/edit_post/<int:post_id>", methods=["GET", "POST"])
def edit_post(post_id):

    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()

    post = conn.execute("""
        SELECT *
        FROM posts
        WHERE id = ? AND user_id = ?
    """, (
        post_id,
        session["user_id"]
    )).fetchone()

    if post is None:

        conn.close()

        return "You cannot edit this post."

    if request.method == "POST":

        title = request.form["title"]
        content = request.form["content"]

        conn.execute("""
            UPDATE posts
            SET title = ?, content = ?
            WHERE id = ? AND user_id = ?
        """, (
            title,
            content,
            post_id,
            session["user_id"]
        ))

        conn.commit()
        conn.close()

        return redirect("/")

    conn.close()

    return render_template(
        "edit_post.html",
        post=post
    )


# ---------------- DELETE POST ----------------

@app.route("/delete_post/<int:post_id>")
def delete_post(post_id):

    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()

    conn.execute(
        "DELETE FROM comments WHERE post_id = ?",
        (post_id,)
    )

    conn.execute(
        "DELETE FROM likes WHERE post_id = ?",
        (post_id,)
    )

    conn.execute("""
        DELETE FROM posts
        WHERE id = ? AND user_id = ?
    """, (
        post_id,
        session["user_id"]
    ))

    conn.commit()
    conn.close()

    return redirect("/")


# ---------------- LIKE ----------------

@app.route("/like/<int:post_id>")
def like(post_id):

    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()

    existing = conn.execute("""
        SELECT *
        FROM likes
        WHERE user_id = ? AND post_id = ?
    """, (
        session["user_id"],
        post_id
    )).fetchone()

    if existing:

        conn.execute("""
            DELETE FROM likes
            WHERE user_id = ? AND post_id = ?
        """, (
            session["user_id"],
            post_id
        ))

    else:

        conn.execute("""
            INSERT INTO likes (user_id, post_id)
            VALUES (?, ?)
        """, (
            session["user_id"],
            post_id
        ))

    conn.commit()
    conn.close()

    return redirect("/")


# ---------------- COMMENT ----------------

@app.route("/comment/<int:post_id>", methods=["POST"])
def comment(post_id):

    if "user_id" not in session:
        return redirect("/login")

    comment_text = request.form["comment"]

    if comment_text.strip() == "":
        return redirect("/")

    conn = get_db()

    conn.execute("""
        INSERT INTO comments (user_id, post_id, comment)
        VALUES (?, ?, ?)
    """, (
        session["user_id"],
        post_id,
        comment_text
    ))

    conn.commit()
    conn.close()

    return redirect("/")


# ---------------- FOLLOW ----------------

@app.route("/follow/<int:user_id>")
def follow(user_id):

    if "user_id" not in session:
        return redirect("/login")

    if user_id == session["user_id"]:
        return redirect("/profile/" + str(user_id))

    conn = get_db()

    existing = conn.execute("""
        SELECT *
        FROM followers
        WHERE follower_id = ? AND following_id = ?
    """, (
        session["user_id"],
        user_id
    )).fetchone()

    if existing:

        conn.execute("""
            DELETE FROM followers
            WHERE follower_id = ? AND following_id = ?
        """, (
            session["user_id"],
            user_id
        ))

    else:

        conn.execute("""
            INSERT INTO followers (follower_id, following_id)
            VALUES (?, ?)
        """, (
            session["user_id"],
            user_id
        ))

    conn.commit()
    conn.close()

    return redirect("/profile/" + str(user_id))


# ---------------- PROFILE ----------------

@app.route("/profile/<int:user_id>")
def profile(user_id):

    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()

    user = conn.execute("""
        SELECT *
        FROM users
        WHERE id = ?
    """, (user_id,)).fetchone()

    if user is None:

        conn.close()

        return "User not found."

    posts = conn.execute("""
        SELECT *
        FROM posts
        WHERE user_id = ?
        ORDER BY created_at DESC
    """, (user_id,)).fetchall()

    followers = conn.execute("""
        SELECT COUNT(*)
        FROM followers
        WHERE following_id = ?
    """, (user_id,)).fetchone()[0]

    following = conn.execute("""
        SELECT COUNT(*)
        FROM followers
        WHERE follower_id = ?
    """, (user_id,)).fetchone()[0]

    is_following = conn.execute("""
        SELECT *
        FROM followers
        WHERE follower_id = ? AND following_id = ?
    """, (
        session["user_id"],
        user_id
    )).fetchone()

    conn.close()

    return render_template(
        "profile.html",
        user=user,
        posts=posts,
        followers=followers,
        following=following,
        is_following=is_following
    )


# ---------------- START APPLICATION ----------------

if __name__ == "__main__":

    init_db()

    app.run(debug=True)