# firebase_service.py
import firebase_admin
from firebase_admin import credentials, firestore, auth, storage, db
import hashlib
from werkzeug.utils import secure_filename
import uuid
import datetime
import tempfile
import os

class FirebaseService:
    def __init__(self):
        # Use the application default credentials or specify path to service account
        # You'll need to generate a service account key from Firebase console
        cred_path = os.environ.get('FIREBASE_CREDENTIALS', 'firebase-credentials.json')
        
        if not firebase_admin._apps:
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred, {
                'storageBucket': 'optima-88380.firebasestorage.app'
            })
            
        self.db = firestore.client()
        self.bucket = storage.bucket()
        
    # Authentication Methods
    def register_user(self, email, password, username):
        try:
            # Create user in Firebase Auth
            user = auth.create_user(
                email=email,
                password=password,
                display_name=username
            )
            
            # Create user document in Firestore
            self.db.collection('users').document(user.uid).set({
                'email': email,
                'username': username,
                'friends': [],
                'createdAt': firestore.SERVER_TIMESTAMP
            })
            
            return {
                'uid': user.uid,
                'email': user.email,
                'displayName': user.display_name
            }
        except Exception as e:
            print(f"Error in register_user: {e}")
            raise e
    
    def login_user(self, email, password):
        try:
            # Firebase Admin SDK doesn't support sign-in with email/password directly
            # In a production app, you would use Firebase Auth REST API or client SDKs
            # Here we'll simulate login by fetching the user by email
            
            # Note: In production, you should use Firebase Auth tokens for authentication
            users = list(self.db.collection('users').where('email', '==', email).limit(1).stream())
            
            if not users:
                raise Exception("User not found")
                
            user_doc = users[0]
            user_id = user_doc.id
            user_data = user_doc.to_dict()
            
            # Check if user document exists, if not create it
            if not user_data:
                # Get auth user
                auth_user = auth.get_user_by_email(email)
                self.db.collection('users').document(user_id).set({
                    'email': email,
                    'username': auth_user.display_name or email.split('@')[0],
                    'friends': [],
                    'createdAt': firestore.SERVER_TIMESTAMP
                })
                user_data = {
                    'email': email,
                    'username': auth_user.display_name or email.split('@')[0],
                    'friends': []
                }
            
            return {
                'uid': user_id,
                'email': user_data.get('email'),
                'displayName': user_data.get('username')
            }
        except Exception as e:
            print(f"Error in login_user: {e}")
            raise e
    
    # User Methods
    def get_user_profile(self, user_id):
        try:
            user_doc = self.db.collection('users').document(user_id).get()
            
            if not user_doc.exists:
                raise Exception("User not found")
                
            user_data = user_doc.to_dict()
            user_data['id'] = user_doc.id
            
            return user_data
        except Exception as e:
            print(f"Error in get_user_profile: {e}")
            raise e
    
    def search_users(self, search_term):
        try:
            # Get users where username starts with search_term
            query = (
                self.db.collection('users')
                .where('username', '>=', search_term)
                .where('username', '<=', search_term + '\uf8ff')
                .limit(10)
            )
            
            users = []
            current_user = None  # In production, get from authenticated context
            
            for doc in query.stream():
                if current_user and doc.id == current_user.uid:
                    continue
                    
                user_data = doc.to_dict()
                user_data['id'] = doc.id
                
                # Check if user is a friend of current user
                if current_user:
                    user_data['isFriend'] = current_user.uid in user_data.get('friends', [])
                    
                users.append(user_data)
                
            return users
        except Exception as e:
            print(f"Error in search_users: {e}")
            raise e
    
    # Friend Methods
    def add_friend(self, user_id, friend_id):
        try:
            # Add friend to user's friends list
            self.db.collection('users').document(user_id).update({
                'friends': firestore.ArrayUnion([friend_id])
            })
            
            # Add user to friend's friends list
            self.db.collection('users').document(friend_id).update({
                'friends': firestore.ArrayUnion([user_id])
            })
            
            return True
        except Exception as e:
            print(f"Error in add_friend: {e}")
            raise e
    
    def remove_friend(self, user_id, friend_id):
        try:
            # Remove friend from user's friends list
            self.db.collection('users').document(user_id).update({
                'friends': firestore.ArrayRemove([friend_id])
            })
            
            # Remove user from friend's friends list
            self.db.collection('users').document(friend_id).update({
                'friends': firestore.ArrayRemove([user_id])
            })
            
            return True
        except Exception as e:
            print(f"Error in remove_friend: {e}")
            raise e
    
    # Post Methods
    def create_post(self, user_id, content):
        try:
            user = self.get_user_profile(user_id)
            post_ref = self.db.collection('posts').document()
            
            post_ref.set({
                'userId': user_id,
                'username': user['username'],
                'content': content,
                'likes': [],
                'comments': [],
                'createdAt': firestore.SERVER_TIMESTAMP
            })
            
            return post_ref.id
        except Exception as e:
            print(f"Error in create_post: {e}")
            raise e
    
    def get_friends_posts(self, user_id):
        try:
            # Get user's friends
            user_doc = self.db.collection('users').document(user_id).get()
            user_data = user_doc.to_dict()
            friends = user_data.get('friends', []) if user_data else []
            
            # Include user's own posts
            friends.append(user_id)
            
            # Get posts from user and friends
            posts = []
            
            # Handle case with no friends
            if not friends:
                return []
                
            query = (
                self.db.collection('posts')
                .where('userId', 'in', friends)
                .order_by('createdAt', direction=firestore.Query.DESCENDING)
                .limit(20)
            )
            
            for doc in query.stream():
                post_data = doc.to_dict()
                # Convert timestamps to strings for JSON serialization
                if 'createdAt' in post_data and post_data['createdAt']:
                    post_data['createdAt'] = post_data['createdAt'].isoformat()
                    
                post_data['id'] = doc.id
                posts.append(post_data)
                
            return posts
        except Exception as e:
            print(f"Error in get_friends_posts: {e}")
            raise e
    
    # Like Methods
    def toggle_like(self, post_id, user_id):
        try:
            post_ref = self.db.collection('posts').document(post_id)
            post_doc = post_ref.get()
            
            if not post_doc.exists:
                raise Exception("Post not found")
                
            post_data = post_doc.to_dict()
            likes = post_data.get('likes', [])
            has_liked = user_id in likes
            
            if has_liked:
                post_ref.update({
                    'likes': firestore.ArrayRemove([user_id])
                })
            else:
                post_ref.update({
                    'likes': firestore.ArrayUnion([user_id])
                })
                
            return not has_liked
        except Exception as e:
            print(f"Error in toggle_like: {e}")
            raise e
    
    def add_comment(self, post_id, user_id, content):
        try:
            user = self.get_user_profile(user_id)
            post_ref = self.db.collection('posts').document(post_id)
            
            comment = {
                'id': str(uuid.uuid4()),
                'userId': user_id,
                'username': user['username'],
                'content': content,
                'createdAt': datetime.datetime.now().isoformat()
            }
            
            post_ref.update({
                'comments': firestore.ArrayUnion([comment])
            })
            
            return comment
        except Exception as e:
            print(f"Error in add_comment: {e}")
            raise e
            
    def get_like_details(self, post_id):
        try:
            likes = []
            post_doc = self.db.collection('posts').document(post_id).get()
            
            if not post_doc.exists:
                raise Exception("Post not found")
                
            like_user_ids = post_doc.to_dict().get('likes', [])
            
            # Get user details for each like
            for user_id in like_user_ids:
                user_doc = self.db.collection('users').document(user_id).get()
                if user_doc.exists:
                    user_data = user_doc.to_dict()
                    likes.append({
                        'userId': user_id,
                        'username': user_data.get('username')
                    })
                    
            return likes
        except Exception as e:
            print(f"Error in get_like_details: {e}")
            raise e
    
    # Additional methods from star.jsx
    def get_post(self, post_id):
        try:
            post_doc = self.db.collection('posts').document(post_id).get()
            
            if not post_doc.exists:
                raise Exception("Post not found")
                
            post_data = post_doc.to_dict()
            post_data['id'] = post_doc.id
            
            # Convert timestamp to string
            if 'createdAt' in post_data and post_data['createdAt']:
                post_data['createdAt'] = post_data['createdAt'].isoformat()
                
            return post_data
        except Exception as e:
            print(f"Error in get_post: {e}")
            raise e
    
    def get_feed(self, user_id, last_post=None):
        try:
            # Create base query
            query = (
                self.db.collection('posts')
                .order_by('createdAt', direction=firestore.Query.DESCENDING)
                .limit(10)
            )
            
            # If last_post provided, use it as start_after
            if last_post:
                last_post_doc = self.db.collection('posts').document(last_post).get()
                if last_post_doc.exists:
                    query = query.start_after(last_post_doc)
                    
            # Execute query
            posts = []
            for doc in query.stream():
                post_data = doc.to_dict()
                post_data['id'] = doc.id
                
                # Convert timestamp to string
                if 'createdAt' in post_data and post_data['createdAt']:
                    post_data['createdAt'] = post_data['createdAt'].isoformat()
                    
                posts.append(post_data)
                
            return {
                'posts': posts,
                'last_post': posts[-1]['id'] if posts else None
            }
        except Exception as e:
            print(f"Error in get_feed: {e}")
            raise e
    
    def get_comments(self, post_id, last_comment=None):
        try:
            # Create base query
            query = (
                self.db.collection('comments')
                .where('post_id', '==', post_id)
                .order_by('createdAt', direction=firestore.Query.DESCENDING)
                .limit(20)
            )
            
            # If last_comment provided, use it as start_after
            if last_comment:
                last_comment_doc = self.db.collection('comments').document(last_comment).get()
                if last_comment_doc.exists:
                    query = query.start_after(last_comment_doc)
                    
            # Execute query
            comments = []
            for doc in query.stream():
                comment_data = doc.to_dict()
                comment_data['id'] = doc.id
                
                # Convert timestamp to string
                if 'createdAt' in comment_data and comment_data['createdAt']:
                    comment_data['createdAt'] = comment_data['createdAt'].isoformat()
                    
                comments.append(comment_data)
                
            return {
                'comments': comments,
                'last_comment': comments[-1]['id'] if comments else None
            }
        except Exception as e:
            print(f"Error in get_comments: {e}")
            raise e
    
    def check_like_status(self, post_id, user_id):
        try:
            like_ref = self.db.collection('likes').document(f"{post_id}_{user_id}").get()
            return like_ref.exists
        except Exception as e:
            print(f"Error in check_like_status: {e}")
            raise e
    
    def toggle_follow(self, follower_id, target_user_id):
        try:
            follower_ref = self.db.collection('users').document(follower_id)
            target_ref = self.db.collection('users').document(target_user_id)
            
            follower_doc = follower_ref.get()
            if not follower_doc.exists:
                raise Exception("Follower user not found")
                
            following = follower_doc.to_dict().get('following', [])
            
            if target_user_id in following:
                # Unfollow
                follower_ref.update({
                    'following': firestore.ArrayRemove([target_user_id])
                })
                target_ref.update({
                    'followers_count': firestore.Increment(-1)
                })
                return False
            else:
                # Follow
                follower_ref.update({
                    'following': firestore.ArrayUnion([target_user_id])
                })
                target_ref.update({
                    'followers_count': firestore.Increment(1)
                })
                return True
        except Exception as e:
            print(f"Error in toggle_follow: {e}")
            raise e
    
    def update_user_profile(self, user_id, updates):
        try:
            updates['updated_at'] = firestore.SERVER_TIMESTAMP
            self.db.collection('users').document(user_id).update(updates)
            return True
        except Exception as e:
            print(f"Error in update_user_profile: {e}")
            raise e
    
    def upload_profile_picture(self, user_id, file):
        try:
            # Create a temporary file
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                file.save(tmp.name)
                
                # Upload to Firebase Storage
                blob = self.bucket.blob(f"profile_pictures/{user_id}")
                blob.upload_from_filename(tmp.name)
                
                # Make the blob publicly accessible
                blob.make_public()
                url = blob.public_url
                
            # Update user profile with picture URL
            self.update_user_profile(user_id, {'profile_picture': url})
            
            # Clean up temp file
            os.unlink(tmp.name)
            
            return {'url': url}
        except Exception as e:
            print(f"Error in upload_profile_picture: {e}")
            raise e
    
    # Admin auth methods
    
    def register_admin(self, email, password, name):
        '''Register a new admin user'''
        try:
            # Check if admin with this email alr exists
            admins_query = self.db.collection('admins').where('email', '==', email).limit(1).stream()
            if list(admins_query):
                raise Exception('Admin with this email already exists')
            
            admins_ref = self.db.collection('admins').document()
            admin_id = admins_ref.id
            
            hashed_password = hashlib.sha256(password.encode()).hexdigest() # hashes the password, to change in prod for more secure hashing
            
            admin_data = {
                'id': admin_id,
                'email': email,
                'password': hashed_password, # to change in prod
                'name': name,
                'created_at': firestore.SERVER_TIMESTAMP
            }
            
            admins_ref.set(admin_data)
            self.log_admin_action(admin_id, 'ADMIN_CREATED', {
                'admin_email': email
            })
            admin_return = admin_data.copy()
            admin_return.pop('password')
            return admin_return
        except Exception as e:
            print(f'Error in register_admin: {e}')
            raise(e)
    
    def login_admin(self, email, password):
        '''Authenticate an admin user'''
        try: 
            hashed_password = hashlib.sha256(password.encode()).hexdigest()
            
            admins_query = self.db.collection('admins').where('email', '==', email).limit(1).stream()
            admins = list(admins_query)
            
            if not admins:
                return None
            
            admin_doc = admins[0]
            admin_data = admin_doc.to_dict()
            
            if admin_data.get('password') != hashed_password:
                return None
            
            admin_return = admin_data.copy()
            admin_return.pop('password')
            admin_return['id'] = admin_doc.id
            
            return admin_return
        except Exception as e:
            print(f'Error in login_admin: {e}')
            raise(e)

    def get_admin(self, admin_id):
        '''Get admin by id'''
        try:
            admin_doc = self.db.collection('admins').document(admin_id).get()
            
            if not admin_doc.exists:
                return None
            
            admin_data = admin_doc.to_dict()
            
            # remove passw from return obj
            admin_return = admin_data.copy()
            admin_return.pop('password', None)
            admin_return['id'] = admin_doc.id
            
            return admin_return
        except Exception as e:
            print(f'Error in get_admin: {e}')
            raise(e)

    # Task management methods
    
    def get_all_tasks(self):
        '''get all task templates'''
        try:
            tasks = []
            task_query = self.db.collection('tasks').stream()
            
            for doc in task_query:
                task_data = doc.to_dict()
                task_data['id'] = doc.id
                tasks.append(task_data)
            
            return tasks
        except Exception as e:
            print(f'Error in get_all_tasks: {e}')
            raise e
    
    def create_task_template(self, title, reward, category='General', description=''): # ? Maybe not to use
        '''Create new task template'''
        try:
            tasks_ref = self.db.collection('tasks').document()
            
            task_data = {
                'title': title,
                'reward': reward,
                'category': category,
                'description': description,
                'created_at': firestore.SERVER_TIMESTAMP
            }
            
            tasks_ref.set(task_data)
            return tasks_ref.id
        except Exception as e:
            print(f'Error in create_task_template: {e}')
            raise e
    
    def update_task(self, task_id, updates):
        '''Update an existing task template'''
        try:
            task_ref = self.db.collection('tasks').document(task_id)
            task_doc = task_ref.get()
            
            if not task_doc.exists:
                raise Exception('Task not found')
            
            updates['UpdatedAt'] = firestore.SERVER_TIMESTAMP
            task_ref.update(updates)
            return True
        except Exception as e:
            print(f'Error in update_task: {e}')
            raise e
    
    def delete_task(self, task_id):
        '''Delete a task template'''
        try:
            task_ref = self.db.collection('tasks').document(task_id)
            task_doc = task_ref.get()
            
            if not task_doc.exists:
                raise Exception('Task not found')
            
            task_ref.delete()
            return True
        except Exception as e:
            print(f'Error in delete_task: {e}')
            raise e
    
    # User management methods
    
    def get_all_users(self):
        '''Get all users with basic info'''
        try:
            users = []
            users_query = self.db.collection('users').stream()
            
            for doc in users_query:
                user_data = doc.to_dict()
                filtered_user = {
                    'id': doc.id,
                    'username': user_data.get('username', ''),
                    'email': user_data.get('email', ''),
                    'createdAt': user_data.get('createdAt', ''),
                    'lastLogin': user_data.get('lastLogin', ''),
                    'suspended': user_data.get('suspended', False)
                }
                users.append(filtered_user)
            return users
        except Exception as e:
            print(f'Error in get_all_users: {e}')
            raise(e)
    
    def get_user_tasks(self, user_id):
        '''Get tasks associated with specific user'''
        try:
            tasks = []
            tasks_query = self.db.collection('user_tasks').where('userId', '==', user_id).stream()
            
            for doc in tasks_query:
                task_data = doc.to_dict()
                task_data['id'] = doc.id
                tasks.append(task_data)
            
            return tasks
        except Exception as e:
            print(F'Error in get_user_tasks: {e}')
            raise e
    
    def get_user_screentime(self, user_id):
        '''Get screentime data for a user'''
        try:
            screentime_query = self.db.collection('screentime').where('userId', '==', user_id).stream()
            screentime_data = [doc.to_dict() for doc in screentime_query]
            
            return screentime_data
        except Exception as e:
            print(f'Error in get_user_screentime: {e}')
            raise(e)

    def reset_user_password(self, user_id, new_password):
        '''Reset a user's password'''
        try:
            user_ref = self.db.collection('users').document(user_id) # TODO: in production environment, it would be best to use firebase auth to reset password
            
            user_doc = user_ref.get()
            if not user_doc.exists:
                raise Exception('User not found')
            
            hashed_password = hashlib.sha256(new_password.encode()).hexdigest() # check back on hashing password functionality
            
            user_ref.update({'password': hashed_password})
            return True
        except Exception as e:
            print(f'Error in reset_user_password: {e}')
            raise(e)
    
    def suspend_user(self, user_id, suspend=True):
        '''Suspend or unsuspend a user account'''
        try:
            user_ref = self.db.collection('users').document(user_id)
            
            user_doc = user_ref.get()
            if not user_doc.exists:
                raise Exception('User not found')
            
            user_ref.update({'suspended': suspend})
            return True
        except Exception as e:
            print(f'Error in suspend_user: {e}')
            raise e
    
    # Post Management methods
    
    def get_all_posts(self, limit=50):
        '''Get all posts with a specific limit'''
        try:
            posts = []
            posts_query = (
                self.db.collection('posts')
                .order_by('createdAt', direction=firestore.Query.DESCENDING)
                .limit(limit)
                .stream()
            )
            
            for doc in posts_query:
                post_data = doc.to_dict()
                post_data['id'] = doc.id
                
                if 'createdAt' in post_data and post_data['createdAt']:
                    post_data['createdAt'] = post_data['createdAt'].isoformat() # converts timestamp to string
                
                posts.append(post_data)
            return posts
        except Exception as e:
            print(f'Error in suspend_user: {e}')
            raise e
    
    def delete_post(self, post_id):
        '''Delete a specified post'''
        try:
            post_ref = self.db.collection('posts').document(post_id)
            post_doc = post_ref.get()
            
            if not post_doc.exists:
                raise Exception('Post not found')
            
            post_ref.delete() # delete post
            
            # ! Next logic will need to be changed depending on how the collections are stored (likes and comments), TBD
            comments_query = self.db.collection('comments').where('post_id', '==', post_id).stream()
            for comment_doc in comments_query:
                comment_doc.reference.delete()  # Use reference to delete the comment
            
            return True
        except Exception as e:
            print(f'Error in delete_post: {e}')
            raise e

    # Analytics methods

    def get_analytics_summary(self): # Can be refactored
        '''Get summary analytics for the dashboard'''
        try:
            # count users
            users_query = self.db.collection('users').stream()
            users_count = len(list(users_query))
            
            # count tasks
            tasks_query = self.db.collection('tasks').stream()
            tasks_count = len(list(tasks_query))
            
            # count posts
            posts_query = self.db.collection('posts').stream()
            posts_count = len(list(posts_query))
            
            # count active users (past 7 days)
            seven_days_ago = datetime.datetime.now() - datetime.timedelta(days=7)
            active_users_query = (
                self.db.collection('users')
                .where('lastLogin', '>=', seven_days_ago)
                .stream()
            )
            active_users_count = len(list(active_users_query))
            
            # count completed tasks
            completed_tasks_query = (
                self.db.collection('tasks')
                .where('completed', '==', True ) # ? Not sure logic here will work properly, again depends on how the db is structured. To be reviewed at next meeting
                .stream()
            )
            completed_tasks_count = len(list(completed_tasks_query))
            
            return {
                'total_users': users_count,
                'active_users_7d': active_users_count,
                'total_tasks': tasks_count,
                'completed_tasks': completed_tasks_count,
                'posts_count': posts_count
            }
        except Exception as e:
            print(f'Error in get_analytics_summary: {e}')
            raise e
    
    def get_task_analytics(self):
        '''Get analytics about tasks usage'''
        try:
            tasks_query = self.db.collection('tasks').stream() # get all tasks and then analyse categories
            
            # count tasks by category
            categories = dict()
            for doc in tasks_query:
                task = doc.to_dict()
                category = task.get('category', 'General')
                categories[category] = categories.get(category, 0) + 1
            
            # Get completion rate
            total_user_tasks_query = self.db.collection('user_tasks').stream()
            total_user_tasks_count = len(list(total_user_tasks_query))
            
            completed_user_tasks_query = (
                self.db.collection('user_tasks')
                .where('completed', '==', True)
                .stream()
            )
            completed_user_tasks_count = len(list(completed_user_tasks_query))
            
            completion_rate = 0
            if total_user_tasks_count > 0:
                completion_rate = (completed_user_tasks_count / total_user_tasks_count) * 100
            
            return {
                'categories': [{'name': k, 'count': v} for k, v in categories.items()],
                'completion_rate': completion_rate,
                'total_tasks_assigned': total_user_tasks_count,
                'tasks_completed': completed_user_tasks_count
            }
        except Exception as e:
            print(f'Error in get_task_analytics: {e}')
            raise e
    
    def get_screentime_analytics(self): # ! This method uses a lot of db logic which might not follow the db structure, TO CHANGE to match associated structure
        '''Get analytics about screentime usage'''
        try:
            # get all screentime records
            screentime_query = self.db.collection('screentime').stream()
            screentime_records = [doc.to_dict() for doc in screentime_query]
            
            # calculate average daily screentime
            total_time = 0
            record_count = 0
            
            for record in screentime_records:
                total_time += record.get('duration', 0)
                record_count += 1
            
            avg_screentime = 0
            if record_count > 0:
                avg_screentime = total_time / record_count
            
            # calculate screentime by day of the week # ! Start of an intended feature of seeing screentime by day, unlikely to work with current structure
            days_of_week = {
            0: 'Monday',
            1: 'Tuesday',
            2: 'Wednesday',
            3: 'Thursday',
            4: 'Friday',
            5: 'Saturday',
            6: 'Sunday'
            }
            
            screentime_by_day = {day: 0 for day in days_of_week.values()}
            counts_by_day = {day: 0 for day in days_of_week.values()}
            
            for record in screentime_records:
                if 'timestamp' in record and record['timestamp']:
                    timestamp = record['timestamp']
                    if isinstance(timestamp, str):
                        timestamp = datetime.datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    day_name = days_of_week[timestamp.weekday()]
                    screentime_by_day[day_name] += record.get('duration', 0)
                    counts_by_day[day_name] += 1
            
            # calculate average by day
            avg_by_day = dict()
            for day in days_of_week.values():
                if counts_by_day[day] > 0:
                    avg_by_day[day] = screentime_by_day[day] / counts_by_day[day]
                else:
                    avg_by_day[day] = 0
            
            return {
                'average_daily_screentime': avg_screentime,
                'screentime_by_day': [{'day': day, 'average': average} for day, average in avg_by_day.items()]
            }
        except Exception as e:
            print(f'Error in get_screentime_analytics: {e}')
            raise e
    
    # Admin logs methods
    
    def log_admin_action(self, admin_id, action_type, details=None, ip_address=None):
        '''Log an action taken/performed by an admin'''
        try:
            log_ref = self.db.collection('admin_logs').document()
            
            log_data = {
                'admin_id': admin_id,
                'action_type': action_type,
                'details': details or dict(),
                'timestamp': firestore.SERVER_TIMESTAMP,
                'ip_address': ip_address # to get from the request in the actual route handler
            }
            
            log_ref.set(log_data)
            return log_ref.id
        except Exception as e:
            print(f'Error in log_admin_actions: {e}')
            raise e
    
    def get_admin_logs(self, limit=100):
        '''Get admin activity logs'''
        try:
            logs = []
            logs_query = (
                self.db.collection('admin_logs')
                .order_by('timestamp', direction=firestore.Query.DESCENDING)
                .limit(limit)
                .stream())
            
            for doc in logs_query:
                log_data = doc.to_dict()
                log_data['id'] = doc.id
                if 'timestamp' in log_data and log_data['timestamp']: # convert time stamp to string if it exists
                    log_data['timestamp'] = log_data['timestamp'].isoformat()
                logs.append(log_data)
            
            return logs
        except Exception as e:
            print(f'Error in get_admins_logs: {e}')
            raise e