import boto3
from botocore.config import Config
import streamlit as st
import database
import graph
import html
import csv
import io
import uuid
from pathlib import Path


# =========================================================
# PAGE CONFIGURATION
# =========================================================

st.set_page_config(
    page_title="CampusConnect",
    page_icon="🎀",
    layout="wide"
)

BASE_DIR = Path(__file__).resolve().parent
PROFILE_FOLDER = BASE_DIR / "uploads" / "profiles"
POST_FOLDER = BASE_DIR / "uploads" / "posts"

PROFILE_FOLDER.mkdir(parents=True, exist_ok=True)
POST_FOLDER.mkdir(parents=True, exist_ok=True)



# =========================================================
# IMAGE UTILITIES - SUPABASE STORAGE
# =========================================================

@st.cache_resource
def get_storage_client():
    storage = st.secrets["storage"]

    return boto3.client(
        "s3",
        endpoint_url=storage["endpoint_url"],
        region_name=storage["region"],
        aws_access_key_id=storage["access_key_id"],
        aws_secret_access_key=storage["secret_access_key"],
        config=Config(signature_version="s3v4")
    )


def save_uploaded_image(uploaded_file, folder):
    if uploaded_file is None:
        return None

    extension = Path(uploaded_file.name).suffix.lower()

    allowed_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp"
    }

    if extension not in allowed_types:
        raise ValueError(
            "Please upload JPG, JPEG, PNG or WEBP."
        )

    image_data = uploaded_file.getvalue()

    if len(image_data) > 5 * 1024 * 1024:
        raise ValueError("Image must be smaller than 5 MB.")

    # Verify that the uploaded file is actually an image.
    try:
        from PIL import Image

        image = Image.open(io.BytesIO(image_data))

        expected_formats = {
            ".jpg": "JPEG",
            ".jpeg": "JPEG",
            ".png": "PNG",
            ".webp": "WEBP"
        }

        if image.format != expected_formats[extension]:
            raise ValueError("Image format does not match its file extension.")

        image.verify()

    except ValueError:
        raise

    except Exception:
        raise ValueError("The uploaded file is not a valid image.")

    folder_name = Path(folder).name

    if folder_name not in ("profiles", "posts"):
        raise ValueError("Invalid image storage location.")

    filename = uuid.uuid4().hex + extension
    object_key = f"uploads/{folder_name}/{filename}"

    storage = st.secrets["storage"]

    try:
        client = get_storage_client()

        client.put_object(
            Bucket=storage["bucket"],
            Key=object_key,
            Body=image_data,
            ContentType=allowed_types[extension]
        )

    except Exception:
        raise ValueError(
            "Image upload failed. Please check your Storage configuration "
            "and try again."
        )

    return object_key


def get_image_path(relative_path):
    if not relative_path:
        return None

    object_key = str(relative_path).replace("\\", "/")

    # Keep compatibility with any existing local image files.
    local_path = BASE_DIR / object_key

    if local_path.exists() and local_path.is_file():
        return local_path

    storage = st.secrets["storage"]

    try:
        client = get_storage_client()

        return client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": storage["bucket"],
                "Key": object_key
            },
            ExpiresIn=3600
        )

    except Exception:
        return None

# =========================================================
# DESIGN
# =========================================================

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@400;500;600&display=swap');

.stApp {
    background-color: #f7f0e6;
    background-image:
        radial-gradient(ellipse at 8% 8%, rgba(201,135,155,0.13), transparent 30%),
        radial-gradient(ellipse at 92% 85%, rgba(201,135,155,0.12), transparent 30%),
        repeating-linear-gradient(
            0deg,
            rgba(118,81,92,0.018) 0px,
            rgba(118,81,92,0.018) 1px,
            transparent 1px,
            transparent 5px
        );
    color: #654653;
    font-family: 'DM Sans', sans-serif;
}

h1, h2, h3 {
    font-family: 'DM Serif Display', serif !important;
    color: #85465e !important;
}

p, label, li {
    color: #765461;
}

[data-testid="stSidebar"] {
    background: #f1dfdc;
    border-right: 1px solid #dfb8c5;
}

[data-testid="stTabs"] button {
    color: #9e526d !important;
    font-weight: 600;
}

[data-testid="stTabs"] button[aria-selected="true"] {
    border-bottom: 3px solid #bd7890 !important;
}

.stButton > button {
    background: #bd7890;
    color: white;
    border: 1px solid #bd7890;
    border-radius: 22px;
    padding: 8px 22px;
    font-weight: 600;
    transition: 0.2s;
}

.stButton > button:hover {
    background: #9e526d;
    color: white;
    border-color: #9e526d;
}

.stTextInput input, .stTextArea textarea {
    background: #fffdf9;
    border: 1px solid #dfb8c5;
    border-radius: 12px;
    color: #654653;
}

[data-testid="stVerticalBlockBorderWrapper"] {
    background: rgba(255, 252, 246, 0.96);
    border: 1px solid #e7c8d1;
    border-radius: 16px;
    padding: 12px;
}

[data-testid="stMetric"] {
    background: #f7e5eb;
    border: 1px solid #e7c8d1;
    border-radius: 15px;
    padding: 15px;
}

hr {
    border-color: #e7c8d1;
}

.stAlert {
    border-radius: 14px;
}

footer, #MainMenu {
    visibility: hidden;
}

.vintage-banner {
    background: linear-gradient(120deg, #f3dce3, #fff4ed);
    padding: 28px;
    border-radius: 18px;
    border: 1px solid #dfb8c5;
    margin-bottom: 25px;
}

.post-card {
    background: #fffdf9;
    border: 1px solid #e7c8d1;
    border-left: 5px solid #c9879b;
    border-radius: 16px;
    padding: 20px;
    margin: 12px 0;
    box-shadow: 0 3px 10px rgba(166, 83, 112, 0.08);
}

.post-author {
    color: #9e526d;
    font-weight: 600;
    font-size: 17px;
}

.post-date {
    color: #b58b98;
    font-size: 12px;
    margin-top: 5px;
}

.post-content {
    color: #654653;
    font-size: 15px;
    margin-top: 16px;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
}

.section-note {
    color: #a65370;
    font-style: italic;
}
</style>
""", unsafe_allow_html=True)


# =========================================================
# HEADER
# =========================================================

st.title("🎀 CampusConnect")

st.markdown("""
<div class="vintage-banner">
    <p style="color:#a65370; font-size:14px; margin-bottom:5px;">
        ✿ YOUR LITTLE CORNER OF CAMPUS ✿
    </p>
    <h1 style="color:#85465e; margin:0;">
        Hello, sunshine! ♡
    </h1>
    <p style="color:#765461; margin-top:8px;">
        Share ideas, discover people and grow together.
    </p>
</div>
""", unsafe_allow_html=True)

st.subheader("Your Campus. Your Community.")
st.write(
    "Connect, collaborate and grow with students at Chanakya University."
)


# =========================================================
# SESSION STATE
# =========================================================

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "username" not in st.session_state:
    st.session_state.username = None

if "admin_logged_in" not in st.session_state:
    st.session_state.admin_logged_in = False

if "admin_username" not in st.session_state:
    st.session_state.admin_username = None


# =========================================================
# LOGOUT HELPERS
# =========================================================

def logout_student():
    st.session_state.logged_in = False
    st.session_state.username = None
    st.rerun()


def logout_admin():
    st.session_state.admin_logged_in = False
    st.session_state.admin_username = None
    st.rerun()


# =========================================================
# ADMIN DASHBOARD
# =========================================================

def show_admin_dashboard():

    st.sidebar.success(
        "Administrator: " + st.session_state.admin_username
    )

    if st.sidebar.button("Admin Logout"):
        logout_admin()

    st.header("🛡️ CampusConnect Admin Dashboard")

    stats = database.get_admin_statistics()

    metric_cols = st.columns(4)

    metric_cols[0].metric(
        "Students",
        stats["students"]
    )

    metric_cols[1].metric(
        "Connections",
        stats["connections"]
    )

    metric_cols[2].metric(
        "Posts",
        stats["posts"]
    )

    metric_cols[3].metric(
        "Verified Students",
        stats["verified"]
    )

    second_row = st.columns(3)

    second_row[0].metric(
        "Likes",
        stats["likes"]
    )

    second_row[1].metric(
        "Comments",
        stats["comments"]
    )

    second_row[2].metric(
        "Unused Verification Records",
        stats["unused_records"]
    )

    dashboard_tabs = st.tabs([
        "Students",
        "Import Verification Records",
        "Posts Moderation",
        "Comments Moderation",
        "Verification Logs"
    ])

    # -----------------------------------------------------
    # STUDENT MANAGEMENT
    # -----------------------------------------------------

    with dashboard_tabs[0]:

        st.subheader("Registered Students")

        students = database.get_all_students_details()

        search_student = st.text_input(
            "Search students",
            placeholder="Search by name, username or registration number"
        )

        filtered_students = []

        for student_record in students:

            username, name, programme, year, bio, skills, picture, reg_no, category, verified = student_record

            searchable = (
                str(username)
                + " "
                + str(name)
                + " "
                + str(reg_no or "")
            ).lower()

            if search_student.lower() in searchable:
                filtered_students.append(student_record)

        st.write(
            "Showing",
            len(filtered_students),
            "student account(s)"
        )

        for student_record in filtered_students:

            (
                username,
                name,
                programme,
                year,
                bio,
                skills,
                picture,
                reg_no,
                category,
                verified
            ) = student_record

            with st.expander(
                f"{name} (@{username})"
            ):

                st.write("**Username:**", username)
                st.write("**Name:**", name)
                st.write("**Programme:**", programme)
                st.write("**Year:**", year)
                st.write("**Registration Number:**", reg_no or "Not recorded")
                st.write("**Category:**", category or "Not recorded")
                st.write(
                    "**Verification Status:**",
                    "Verified" if verified else "Legacy / Unverified"
                )
                st.write("**Bio:**", bio)
                st.write("**Skills:**", skills)

                student_image = get_image_path(picture)

                if student_image:
                    st.image(str(student_image), width=120)

                st.warning(
                    "Deleting a student permanently removes their "
                    "CampusConnect account, connections, posts, likes "
                    "and comments."
                )

                confirm_delete = st.checkbox(
                    "Confirm student deletion",
                    key="admin_confirm_delete_" + username
                )

                if st.button(
                    "Delete Student Account",
                    key="admin_delete_student_" + username
                ):

                    if confirm_delete:
                        deleted = database.delete_student_admin(
                            username
                        )

                        if deleted:
                            st.success("Student account deleted.")
                            st.rerun()

                        else:
                            st.error("Could not delete account.")

                    else:
                        st.error(
                            "Please confirm deletion first."
                        )

    # -----------------------------------------------------
    # IMPORT VERIFICATION DATABASE
    # -----------------------------------------------------

    with dashboard_tabs[1]:

        st.subheader("Import Official Student Records")

        st.write("""
        Upload an authorized CSV file exported from your university's
        student registration system.

        Required columns:
        `registration_number`, `full_name`, `category`, `joining_year`
        """)

        st.info("""
        Supported categories:
        UG, PG, Doctorate, Professor

        UG/PG/Doctorate registration numbers follow the format:
        25UG00429, 24PG00115, 23DR00012.

        Professor/faculty registration numbers can use the university's
        faculty ID format, provided the official CSV contains them.
        """)

        csv_file = st.file_uploader(
            "Upload official verification CSV",
            type=["csv"],
            key="admin_student_csv"
        )

        if csv_file:

            csv_bytes = csv_file.getvalue()

            try:
                csv_text = csv_bytes.decode("utf-8-sig")

            except UnicodeDecodeError:
                try:
                    csv_text = csv_bytes.decode("latin-1")

                except Exception:
                    csv_text = ""

            if csv_text:

                st.caption(
                    "Preview of the uploaded CSV file"
                )

                try:
                    preview = csv.DictReader(
                        io.StringIO(csv_text)
                    )

                    preview_rows = list(preview)

                    st.dataframe(
                        preview_rows[:20],
                        use_container_width=True
                    )

                except Exception:
                    st.warning(
                        "Could not preview this file. "
                        "Check that it is a valid CSV."
                    )

                if st.button(
                    "Import / Update Verification Records"
                ):

                    imported, errors = (
                        database.import_verified_records(
                            csv_text
                        )
                    )

                    if imported:
                        st.success(
                            f"Imported or updated {imported} record(s)."
                        )

                    if errors:
                        for error in errors:
                            st.error(error)

        st.divider()

        st.subheader("Current Official Verification Records")

        verified_records = database.get_verified_records()

        if verified_records:

            for record in verified_records:

                reg_no, full_name, category, joining_year, registered_username, imported_at = record

                with st.expander(
                    f"{reg_no} — {full_name}"
                ):

                    st.write("Category:", category)
                    st.write("Joining year:", joining_year)
                    st.write(
                        "Registered account:",
                        registered_username or "Unused"
                    )
                    st.caption("Imported at: " + str(imported_at))

                    if not registered_username:

                        if st.button(
                            "Remove Verification Record",
                            key="remove_verification_" + reg_no
                        ):

                            database.delete_verified_record(
                                reg_no
                            )

                            st.success("Record removed.")
                            st.rerun()

        else:
            st.info(
                "No official records imported yet."
            )

    # -----------------------------------------------------
    # POSTS MODERATION
    # -----------------------------------------------------

    with dashboard_tabs[2]:

        st.subheader("Posts Moderation")

        posts = database.get_all_posts_admin()

        if posts:

            for post in posts:

                post_id, post_username, content, created_at, image_path = post

                post_student = database.get_student(
                    post_username
                )

                post_name = (
                    post_student[2]
                    if post_student
                    else post_username
                )

                with st.expander(
                    f"Post #{post_id} — {post_name}"
                ):

                    st.write("Author:", post_username)
                    st.write("Date:", created_at)
                    st.write(content)

                    post_image = get_image_path(image_path)

                    if post_image:
                        st.image(str(post_image))

                    st.warning(
                        "Admin deletion permanently removes this post "
                        "and its associated likes and comments."
                    )

                    if st.button(
                        "Delete Post",
                        key="admin_delete_post_" + str(post_id)
                    ):

                        database.delete_post_admin(post_id)

                        st.success("Post deleted.")
                        st.rerun()

        else:
            st.info("No posts found.")

    # -----------------------------------------------------
    # COMMENTS MODERATION
    # -----------------------------------------------------

    with dashboard_tabs[3]:

        st.subheader("Comments Moderation")

        comments = database.get_all_comments_admin()

        if comments:

            for comment in comments:

                comment_id, post_id, comment_username, comment_text, created_at = comment

                with st.container(border=True):

                    st.write(
                        f"Comment #{comment_id} on Post #{post_id}"
                    )

                    st.write("Author:", comment_username)
                    st.write(comment_text)
                    st.caption(created_at)

                    if st.button(
                        "Delete Comment",
                        key="admin_delete_comment_" + str(comment_id)
                    ):

                        database.delete_comment_admin(
                            comment_id
                        )

                        st.success("Comment removed.")
                        st.rerun()

        else:
            st.info("No comments found.")

    # -----------------------------------------------------
    # VERIFICATION LOGS
    # -----------------------------------------------------

    with dashboard_tabs[4]:

        st.subheader("Verification Activity")

        logs = database.get_verification_logs()

        if logs:

            st.dataframe(
                [
                    {
                        "Registration Number": row[0],
                        "Category": row[1],
                        "Result": row[2],
                        "Time": row[3]
                    }
                    for row in logs
                ],
                use_container_width=True
            )

        else:
            st.info("No verification activity yet.")


# =========================================================
# ADMIN SESSION
# =========================================================

if st.session_state.admin_logged_in:

    show_admin_dashboard()

    st.stop()


# =========================================================
# STUDENT SESSION
# =========================================================

if st.session_state.logged_in:

    username = st.session_state.username
    student = database.get_student(username)

    if not student:
        logout_student()

    student_graph = graph.load_graph_from_database()

    st.sidebar.success(
        "Logged in as " + student[2]
    )

    sidebar_picture = get_image_path(student[7])

    if sidebar_picture:
        st.sidebar.image(
            str(sidebar_picture),
            width=110
        )

    if st.sidebar.button("Student Logout"):
        logout_student()

    feed_tab, profile_tab, discover_tab, requests_tab, network_tab = st.tabs([
        "Home Feed",
        "My Profile",
        "Discover Students",
        "Connection Requests",
        "My Network"
    ])

    # =====================================================
    # HOME FEED
    # =====================================================

    with feed_tab:

        st.header("Your Home Feed")

        st.markdown(
            '<p class="section-note">A little space for your ideas and inspirations ♡</p>',
            unsafe_allow_html=True
        )

        post_content = st.text_area(
            "What's on your mind?",
            placeholder="Share something interesting with your campus..."
        )

        post_image = st.file_uploader(
            "Add an image to your post (optional)",
            type=["jpg", "jpeg", "png", "webp"],
            key="post_image_upload"
        )

        if st.button("Publish Post ♡"):

            if not post_content.strip() and post_image is None:
                st.warning("Please write something or upload an image.")

            else:

                try:
                    image_path = save_uploaded_image(
                        post_image,
                        POST_FOLDER
                    )

                    database.add_post(
                        username,
                        post_content.strip(),
                        image_path
                    )

                    st.success("Your post has been published!")
                    st.rerun()

                except ValueError as error:
                    st.error(str(error))

        st.divider()
        st.subheader("✿ Recent Posts")

        allowed_users = set(
            student_graph.get_connections(username)
        )

        allowed_users.add(username)

        all_posts = database.get_all_posts()

        feed_posts = [
            post for post in all_posts
            if post[1] in allowed_users
        ]

        feed_posts.sort(
            key=lambda post: post[3],
            reverse=True
        )

        if feed_posts:

            for post in feed_posts:

                post_id, post_username, content, created_at, image_path = post

                post_student = database.get_student(
                    post_username
                )

                if post_student:

                    safe_name = html.escape(
                        str(post_student[2])
                    )

                    safe_username = html.escape(
                        str(post_username)
                    )

                    safe_date = html.escape(
                        str(created_at)
                    )

                    safe_content = html.escape(
                        str(content or "")
                    )

                    st.markdown(f"""
                    <div class="post-card">
                        <div class="post-author">♡ {safe_name}</div>
                        <div class="post-date">@{safe_username} · {safe_date}</div>
                        <div class="post-content">{safe_content}</div>
                        <div style="color:#c9879b; margin-top:15px;">✿ ───────── ♡</div>
                    </div>
                    """, unsafe_allow_html=True)

                    post_image_path = get_image_path(
                        image_path
                    )

                    if post_image_path:
                        st.image(
                            str(post_image_path),
                            use_container_width=True
                        )

                    # LIKES
                    like_count = database.get_post_like_count(
                        post_id
                    )

                    already_liked = database.user_liked_post(
                        post_id,
                        username
                    )

                    like_label = (
                        "♡ Unlike"
                        if already_liked
                        else "♡ Like"
                    )

                    like_col, comment_col = st.columns([1, 3])

                    with like_col:

                        if st.button(
                            f"{like_label} · {like_count}",
                            key="like_post_" + str(post_id)
                        ):

                            database.toggle_post_like(
                                post_id,
                                username
                            )

                            st.rerun()

                    comments = database.get_post_comments(
                        post_id
                    )

                    with comment_col:
                        st.caption(
                            f"💬 {len(comments)} comment(s)"
                        )

                    # COMMENTS
                    with st.expander("Comments"):

                        if comments:

                            for (
                                comment_id,
                                comment_username,
                                comment_text,
                                comment_date
                            ) in comments:

                                commenter = database.get_student(
                                    comment_username
                                )

                                commenter_name = (
                                    commenter[2]
                                    if commenter
                                    else comment_username
                                )

                                st.write(
                                    f"**{commenter_name}** "
                                    f"(@{comment_username})"
                                )

                                st.write(comment_text)
                                st.caption(comment_date)

                                if comment_username == username:

                                    if st.button(
                                        "Delete Comment",
                                        key="delete_comment_" + str(comment_id)
                                    ):

                                        database.delete_comment(
                                            comment_id,
                                            username
                                        )

                                        st.rerun()

                                st.divider()

                        else:
                            st.caption(
                                "No comments yet. Start the conversation!"
                            )

                        with st.form(
                            key="comment_form_" + str(post_id)
                        ):

                            new_comment = st.text_area(
                                "Write a comment",
                                key="comment_text_" + str(post_id),
                                max_chars=1000
                            )

                            submit_comment = st.form_submit_button(
                                "Add Comment"
                            )

                        if submit_comment:

                            if not new_comment.strip():
                                st.warning(
                                    "Please enter a comment."
                                )

                            else:

                                database.add_comment(
                                    post_id,
                                    username,
                                    new_comment.strip()
                                )

                                st.success("Comment added!")
                                st.rerun()

                    # DELETE OWN POST
                    if post_username == username:

                        if st.button(
                            "Delete Post",
                            key="delete_post_" + str(post_id)
                        ):

                            database.delete_post(
                                post_id,
                                username
                            )

                            st.success("Post deleted.")
                            st.rerun()

        else:
            st.info(
                "No posts yet. Share your first idea! ♡"
            )

    # =====================================================
    # PROFILE
    # =====================================================

    with profile_tab:

        st.header("My Profile")

        st.subheader("Edit Profile")

        with st.form(
            key="edit_profile_form_" + username
        ):

            edited_name = st.text_input(
                "Full name",
                value=student[2]
            )

            edited_programme = st.text_input(
                "Programme",
                value=student[3] or ""
            )

            edited_year = st.number_input(
                "Year of study",
                min_value=1,
                max_value=10,
                value=int(student[4] or 1)
            )

            edited_bio = st.text_area(
                "Short bio",
                value=student[5] or "",
                max_chars=500
            )

            edited_skills = st.text_input(
                "Skills (comma separated)",
                value=student[6] or ""
            )

            save_profile = st.form_submit_button(
                "Save Profile Changes ♡"
            )

        if save_profile:

            if not edited_name.strip():
                st.error("Name cannot be empty.")

            else:

                success = database.update_student_profile(
                    username,
                    edited_name,
                    edited_programme,
                    int(edited_year),
                    edited_bio,
                    edited_skills
                )

                if success:
                    st.success("Profile updated!")
                    st.rerun()

                else:
                    st.error("Could not update profile.")

        st.divider()

        st.subheader("Profile Picture")

        profile_picture = get_image_path(student[7])

        if profile_picture:
            st.image(
                str(profile_picture),
                width=180
            )

        new_picture = st.file_uploader(
            "Choose a profile picture",
            type=["jpg", "jpeg", "png", "webp"],
            key="profile_picture_upload"
        )

        if st.button("Save Profile Picture"):

            if not new_picture:
                st.warning("Please choose an image.")

            else:

                try:

                    image_path = save_uploaded_image(
                        new_picture,
                        PROFILE_FOLDER
                    )

                    database.update_profile_picture(
                        username,
                        image_path
                    )

                    st.success("Profile picture updated.")
                    st.rerun()

                except ValueError as error:
                    st.error(str(error))

        st.divider()

        st.subheader("My Information")

        st.write("**Name:**", student[2])
        st.write("**Username:**", username)
        st.write("**Programme:**", student[3])
        st.write("**Year:**", student[4])

        if len(student) > 8:
            st.write(
                "**Registration Number:**",
                student[8] or "Not recorded"
            )

        if len(student) > 9:
            st.write(
                "**Category:**",
                student[9] or "Not recorded"
            )

        if len(student) > 10:
            st.write(
                "**Verification:**",
                "Verified" if student[10] else "Legacy account"
            )

        st.write("**Bio:**", student[5] or "No bio added.")

        st.write("**Skills:**", student[6] or "No skills added.")

        st.divider()

        my_connections = student_graph.get_connections(
            username
        )

        my_posts = [
            post for post in database.get_all_posts()
            if post[1] == username
        ]

        metric_col1, metric_col2 = st.columns(2)

        metric_col1.metric(
            "Connections",
            len(my_connections)
        )

        metric_col2.metric(
            "My Posts",
            len(my_posts)
        )

    # =====================================================
    # DISCOVER STUDENTS
    # =====================================================

    with discover_tab:

        st.header("Discover Students")

        search = st.text_input(
            "Search by name or username"
        )

        all_usernames = database.get_all_students()

        search_results = []

        for other_username in all_usernames:

            if other_username == username:
                continue

            other_student = database.get_student(
                other_username
            )

            if not other_student:
                continue

            if (
                not search
                or search.lower() in other_student[2].lower()
                or search.lower() in other_username.lower()
            ):

                search_results.append(
                    other_student
                )

        if search_results:

            for other_student in search_results:

                other_username = other_student[0]

                with st.container(border=True):

                    other_picture = get_image_path(
                        other_student[7]
                    )

                    if other_picture:
                        st.image(
                            str(other_picture),
                            width=100
                        )

                    st.subheader(other_student[2])

                    st.write("Username:", other_username)
                    st.write("Programme:", other_student[3])
                    st.write("Year:", other_student[4])
                    st.write("Bio:", other_student[5])
                    st.write("Skills:", other_student[6])

                    connected = (
                        other_username
                        in student_graph.get_connections(username)
                    )

                    outgoing = (
                        other_username
                        in database.get_sent_requests(username)
                    )

                    incoming = (
                        username
                        in database.get_sent_requests(other_username)
                    )

                    if connected:
                        st.success("Already connected")

                    elif outgoing:

                        st.info("Request sent")

                        if st.button(
                            "Cancel Request",
                            key="cancel_" + other_username
                        ):

                            database.cancel_request(
                                username,
                                other_username
                            )

                            st.rerun()

                    elif incoming:
                        st.info(
                            "They have sent you a request. "
                            "Check Connection Requests."
                        )

                    else:

                        if st.button(
                            "Connect",
                            key="connect_" + other_username
                        ):

                            success = database.send_request(
                                username,
                                other_username
                            )

                            if success:
                                st.success("Request sent!")

                            else:
                                st.error("Could not send request.")

                            st.rerun()

        else:
            st.info("No students found.")

        st.divider()
        st.subheader("People You May Know")

        suggestions = student_graph.suggest_connections(
            username
        )

        if suggestions:

            for suggested_username, mutual_count in suggestions:

                suggested_student = database.get_student(
                    suggested_username
                )

                if suggested_student:

                    st.write(
                        f"**{suggested_student[2]}** "
                        f"(@{suggested_username})"
                    )

                    st.caption(
                        str(mutual_count)
                        + " mutual connections"
                    )

                    connected = (
                        suggested_username
                        in student_graph.get_connections(username)
                    )

                    outgoing = (
                        suggested_username
                        in database.get_sent_requests(username)
                    )

                    incoming = (
                        username
                        in database.get_sent_requests(suggested_username)
                    )

                    if not connected and not outgoing and not incoming:

                        if st.button(
                            "Connect",
                            key="suggest_connect_" + suggested_username
                        ):

                            database.send_request(
                                username,
                                suggested_username
                            )

                            st.success("Request sent!")
                            st.rerun()

        else:
            st.info("No suggestions available.")

    # =====================================================
    # CONNECTION REQUESTS
    # =====================================================

    with requests_tab:

        st.header("Connection Requests")

        st.subheader("Incoming Requests")

        incoming_requests = database.get_pending_requests(
            username
        )

        if incoming_requests:

            for sender in incoming_requests:

                sender_student = database.get_student(
                    sender
                )

                if sender_student:

                    st.write(
                        f"**{sender_student[2]}** (@{sender})"
                    )

                    col1, col2 = st.columns(2)

                    with col1:

                        if st.button(
                            "Accept",
                            key="accept_" + sender
                        ):

                            database.accept_request(
                                sender,
                                username
                            )

                            st.success("Connected!")
                            st.rerun()

                    with col2:

                        if st.button(
                            "Reject",
                            key="reject_" + sender
                        ):

                            database.reject_request(
                                sender,
                                username
                            )

                            st.rerun()

        else:
            st.info("No incoming requests.")

        st.divider()
        st.subheader("Outgoing Requests")

        outgoing_requests = database.get_sent_requests(
            username
        )

        if outgoing_requests:

            for receiver in outgoing_requests:

                receiver_student = database.get_student(
                    receiver
                )

                if receiver_student:

                    st.write(
                        receiver_student[2]
                        + " (@"
                        + receiver
                        + ")"
                    )

                    if st.button(
                        "Cancel",
                        key="outgoing_cancel_" + receiver
                    ):

                        database.cancel_request(
                            username,
                            receiver
                        )

                        st.rerun()

        else:
            st.info("No outgoing requests.")

    # =====================================================
    # MY NETWORK
    # =====================================================

    with network_tab:

        st.header("My Network")

        my_connections = student_graph.get_connections(
            username
        )

        st.metric(
            "Total Connections",
            len(my_connections)
        )

        if my_connections:

            for connection_username in sorted(
                my_connections
            ):

                connection_student = database.get_student(
                    connection_username
                )

                if connection_student:

                    with st.container(border=True):

                        connection_picture = get_image_path(
                            connection_student[7]
                        )

                        if connection_picture:
                            st.image(
                                str(connection_picture),
                                width=100
                            )

                        st.subheader(
                            connection_student[2]
                        )

                        st.write(
                            "Username:",
                            connection_username
                        )

                        st.write(
                            "Programme:",
                            connection_student[3]
                        )

                        if st.button(
                            "Remove Connection",
                            key="remove_" + connection_username
                        ):

                            database.remove_connection(
                                username,
                                connection_username
                            )

                            st.rerun()

        else:
            st.info("Your network is empty.")

        st.divider()
        st.subheader("Find Mutual Connections")

        other_students = [
            name
            for name in database.get_all_students()
            if name != username
        ]

        if other_students:

            selected_student = st.selectbox(
                "Choose a student",
                other_students
            )

            mutual = student_graph.mutual_connections(
                username,
                selected_student
            )

            st.write(
                "Mutual connections:",
                len(mutual)
            )

            for mutual_username in sorted(mutual):

                mutual_student = database.get_student(
                    mutual_username
                )

                if mutual_student:
                    st.write(
                        "🎓 " + mutual_student[2]
                    )

            st.divider()
            st.subheader("Shortest Connection Chain")

            destination = st.selectbox(
                "Find your connection to",
                other_students,
                key="shortest_destination"
            )

            path = student_graph.shortest_chain(
                username,
                destination
            )

            if path:

                degree = len(path) - 1

                st.success(
                    "Connection degree: " + str(degree)
                )

                st.write("Shortest chain:")

                for index, path_username in enumerate(path):

                    path_student = database.get_student(
                        path_username
                    )

                    if path_student:

                        st.write(
                            str(index + 1)
                            + ". "
                            + path_student[2]
                            + " (@"
                            + path_username
                            + ")"
                        )

                if degree == 1:
                    st.info("1st-degree connection.")

                elif degree == 2:
                    st.info("2nd-degree connection.")

                elif degree == 3:
                    st.info("3rd-degree connection.")

                else:
                    st.info(
                        str(degree)
                        + " connections away."
                    )

            else:
                st.warning("No connection path found.")

        else:
            st.info("Register more students to explore the network.")


# =========================================================
# NOT LOGGED IN: AUTHENTICATION
# =========================================================

else:

    login_tabs = st.tabs([
        "Student / Faculty Login",
        "Verified Registration",
        "Admin Login"
    ])

    # =====================================================
    # STUDENT LOGIN
    # =====================================================

    with login_tabs[0]:

        st.header("Student / Faculty Login")

        login_username = st.text_input(
            "Username",
            key="student_login_username"
        )

        login_password = st.text_input(
            "Password",
            type="password",
            key="student_login_password"
        )

        if st.button("Student Login"):

            if database.login_student(
                login_username.strip(),
                login_password
            ):

                student_record = database.get_student(
                    login_username.strip()
                )

                if student_record:

                    st.session_state.logged_in = True
                    st.session_state.username = login_username.strip()
                    st.rerun()

            else:
                st.error("Incorrect username or password.")

    # =====================================================
    # VERIFIED STUDENT REGISTRATION
    # =====================================================

    with login_tabs[1]:

        st.header("Verified Student Registration")

        st.info(
            "You must have a valid registration record in the "
            "university verification database before creating "
            "a CampusConnect account."
        )

        with st.form("verified_signup_form"):

            reg_number = st.text_input(
                "University Registration Number",
                placeholder="Example: 25UG00429"
            )

            category = st.selectbox(
                "Category",
                [
                    "UG",
                    "PG",
                    "Doctorate",
                    "Professor"
                ]
            )

            full_name = st.text_input(
                "Full name as per university records"
            )

            username_new = st.text_input(
                "Choose username"
            )

            password_new = st.text_input(
                "Create password (minimum 8 characters)",
                type="password"
            )

            confirm_password = st.text_input(
                "Confirm password",
                type="password"
            )

            programme = st.text_input(
                "Programme / Department"
            )

            year = st.number_input(
                "Year of study",
                min_value=1,
                max_value=10,
                value=1
            )

            bio = st.text_area(
                "Bio (optional)"
            )

            skills = st.text_input(
                "Skills (comma separated)"
            )

            register_button = st.form_submit_button(
                "Verify & Register"
            )

        if register_button:

            if not reg_number.strip():
                st.error("Registration number is required.")

            elif not full_name.strip():
                st.error("Full name is required.")

            elif not username_new.strip():
                st.error("Username is required.")

            elif len(password_new) < 8:
                st.error("Password must be at least 8 characters.")

            elif password_new != confirm_password:
                st.error("Passwords do not match.")

            else:

                verified, message, record = (
                    database.verify_registration(
                        reg_number,
                        category,
                        full_name
                    )
                )

                if not verified:
                    st.error(message)

                else:

                    success, registration_message = (
                        database.complete_verified_registration(
                            reg_number,
                            username_new,
                            password_new,
                            full_name,
                            category,
                            programme,
                            int(year),
                            bio,
                            skills
                        )
                    )

                    if success:

                        st.success(
                            registration_message
                            + " You may now log in."
                        )

                    else:
                        st.error(registration_message)

    # =====================================================
    # ADMIN LOGIN
    # =====================================================

    with login_tabs[2]:

        st.header("Administrator Login")

        st.warning(
            "Restricted area. This login is only for authorized "
            "CampusConnect administrators."
        )

        admin_username = st.text_input(
            "Admin Username",
            key="admin_login_username"
        )

        admin_password = st.text_input(
            "Admin Password",
            type="password",
            key="admin_login_password"
        )

        if st.button("Admin Login"):

            if database.login_admin(
                admin_username,
                admin_password
            ):

                st.session_state.admin_logged_in = True
                st.session_state.admin_username = admin_username.strip()
                st.rerun()

            else:
                st.error("Invalid administrator credentials.")