from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from matching_system import ResumeMatchingSystem
import os
import json
import pandas as pd

app = Flask(__name__)
app.secret_key = 'resume_matching_app_secret_key'

# Create data directory if it doesn't exist
data_dir = os.path.join(os.path.dirname(__file__), 'data')
if not os.path.exists(data_dir):
    os.makedirs(data_dir)

# Initialize the matching system
matching_system = ResumeMatchingSystem()

# File paths
candidate_file = os.path.join(data_dir, 'candidates.csv')
job_file = os.path.join(data_dir, 'jobs.csv')
skill_file = os.path.join(data_dir, 'skills.csv')

# Load data if files exist
if os.path.exists(candidate_file):
    matching_system.load_candidates_from_csv(candidate_file)
if os.path.exists(job_file):
    matching_system.load_jobs_from_csv(job_file)
if os.path.exists(skill_file):
    matching_system.load_skill_relationships_from_csv(skill_file)

@app.route('/')
def index():
    stats = {
        'candidates': len(matching_system.candidates),
        'jobs': len(matching_system.jobs),
        'skills': len(matching_system.get_all_skills()),
    }
    return render_template('index.html', stats=stats)

@app.route('/candidates', methods=['GET', 'POST'])
def candidates():
    if request.method == 'POST':
        try:
            candidate_id = int(request.form.get('candidate_id'))
            name = request.form.get('name')
            
            # Parse skills from form as a dictionary
            skills_dict = {}
            skills_data = request.form.getlist('skill_name[]')
            skill_levels = request.form.getlist('skill_level[]')
            
            for i, skill in enumerate(skills_data):
                if skill:  # Skip empty skills
                    skills_dict[skill] = int(skill_levels[i])
            
            experience_years = int(request.form.get('experience_years', 0))
            salary_expectation = float(request.form.get('salary_expectation', 0))
            
            matching_system.add_candidate(
                candidate_id, name, skills_dict, experience_years, salary_expectation
            )
            flash('Candidate added successfully!', 'success')
        except Exception as e:
            flash(f'Error adding candidate: {str(e)}', 'danger')
    
    return render_template('candidates.html', candidates=matching_system.candidates)

@app.route('/candidates/delete/<int:candidate_id>', methods=['POST'])
def delete_candidate(candidate_id):
    # Find and remove candidate
    for i, candidate in enumerate(matching_system.candidates):
        if candidate['id'] == candidate_id:
            matching_system.candidates.pop(i)
            flash('Candidate deleted successfully!', 'success')
            break
    return redirect(url_for('candidates'))

@app.route('/jobs', methods=['GET', 'POST'])
def jobs():
    if request.method == 'POST':
        try:
            job_id = int(request.form.get('job_id'))
            title = request.form.get('title')
            
            # Parse required skills
            required_skills = request.form.getlist('required_skill[]')
            required_skills = [s for s in required_skills if s]  # Remove empty entries
            
            # Parse importance weights
            weights = {}
            for i, skill in enumerate(required_skills):
                weight_value = request.form.getlist('weight[]')[i]
                weights[skill] = float(weight_value) if weight_value else 1.0
            
            # Parse salary range
            min_salary = float(request.form.get('min_salary', 0))
            max_salary = float(request.form.get('max_salary', 0))
            salary_range = (min_salary, max_salary)
            
            matching_system.add_job(job_id, title, required_skills, weights, salary_range)
            flash('Job added successfully!', 'success')
        except Exception as e:
            flash(f'Error adding job: {str(e)}', 'danger')
    
    return render_template('jobs.html', jobs=matching_system.jobs)

@app.route('/jobs/delete/<int:job_id>', methods=['POST'])
def delete_job(job_id):
    # Find and remove job
    for i, job in enumerate(matching_system.jobs):
        if job['id'] == job_id:
            matching_system.jobs.pop(i)
            flash('Job deleted successfully!', 'success')
            break
    return redirect(url_for('jobs'))

@app.route('/skills', methods=['GET', 'POST'])
def skills():
    if request.method == 'POST':
        try:
            skill1 = request.form.get('skill1')
            skill2 = request.form.get('skill2')
            weight = float(request.form.get('weight', 1.0))
            
            matching_system.add_skill_relationship(skill1, skill2, weight)
            flash('Skill relationship added successfully!', 'success')
        except Exception as e:
            flash(f'Error adding skill relationship: {str(e)}', 'danger')
    
    # Get all skills and relationships
    all_skills = matching_system.get_all_skills()
    
    # Prepare edge data for display
    edges = []
    for u, v, data in matching_system.skill_graph.edges(data=True):
        edges.append({
            'source': u,
            'target': v,
            'weight': data.get('weight', 1.0)
        })
    
    # Get skill graph visualization
    skill_graph_img = None
    if matching_system.skill_graph.number_of_nodes() > 0:
        skill_graph_img = matching_system.visualize_skill_graph(return_base64=True)
    
    return render_template('skills.html', skills=all_skills, edges=edges, skill_graph_img=skill_graph_img)

@app.route('/matching', methods=['GET', 'POST'])
def matching():
    if request.method == 'POST':
        threshold = float(request.form.get('threshold', 5))
        matching_system.set_min_score(threshold)
    
    # Check if we have data to perform matching
    if not matching_system.candidates or not matching_system.jobs:
        flash('You need at least one candidate and one job to perform matching!', 'warning')
        return render_template('matching.html')
    
    # Calculate suitability scores
    matching_system.calculate_suitability_scores()
    
    # Find optimal matches
    matches = matching_system.find_optimal_matches()
    
    # Generate report
    report_df = matching_system.generate_report(matches)
    
    # Convert DataFrame to HTML table
    report_html = report_df.to_html(classes="table table-striped table-hover", index=False)
    
    # Determine if the matrix is large
    is_large_matrix = (len(matching_system.candidates) > 10 or len(matching_system.jobs) > 10)
    
    # Get suitability matrix visualization - hide annotations for large matrices
    suitability_img = matching_system.visualize_suitability(return_base64=True, show_annotations=not is_large_matrix)
    
    # Get HTML table representation
    suitability_table_html = matching_system.get_suitability_as_html()
    
    return render_template(
        'matching.html',
        matches=matches,
        report_html=report_html,
        suitability_img=suitability_img,
        suitability_table_html=suitability_table_html,
        threshold=matching_system.min_score_threshold,
        is_large_matrix=is_large_matrix
    )

@app.route('/save_data', methods=['POST'])
def save_data():
    try:
        # Save candidates to CSV - properly serialize complex data
        if matching_system.candidates:
            # Create a copy of candidates with serialized fields
            serialized_candidates = []
            for candidate in matching_system.candidates:
                c = candidate.copy()
                # Convert datetime to string
                if 'application_date' in c:
                    c['application_date'] = c['application_date'].strftime('%Y-%m-%d %H:%M:%S')
                # Convert skills to JSON string
                if 'skills' in c:
                    c['skills'] = json.dumps(c['skills'])
                serialized_candidates.append(c)
            
            candidate_df = pd.DataFrame(serialized_candidates)
            candidate_df.to_csv(candidate_file, index=False)
            print(f"Saved {len(serialized_candidates)} candidates to {candidate_file}")
        
        # Save jobs to CSV - convert dictionaries to string format
        if matching_system.jobs:
            jobs_data = []
            for job in matching_system.jobs:
                job_dict = job.copy()
                job_dict['required_skills'] = json.dumps(job_dict['required_skills'])
                job_dict['importance_weights'] = json.dumps(job_dict['importance_weights'])
                job_dict['salary_range'] = str(job_dict['salary_range'])
                jobs_data.append(job_dict)
            
            job_df = pd.DataFrame(jobs_data)
            job_df.to_csv(job_file, index=False)
            print(f"Saved {len(jobs_data)} jobs to {job_file}")
        
        # Save skill relationships to CSV
        if matching_system.skill_graph.number_of_edges() > 0:
            skill_data = []
            for u, v, data in matching_system.skill_graph.edges(data=True):
                skill_data.append([u, v, data.get('weight', 1.0)])
            
            skill_df = pd.DataFrame(skill_data, columns=['skill1', 'skill2', 'weight'])
            skill_df.to_csv(skill_file, index=False)
            print(f"Saved {len(skill_data)} skill relationships to {skill_file}")
        
        flash('Data saved successfully!', 'success')
    except Exception as e:
        flash(f'Error saving data: {str(e)}', 'danger')
    
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
