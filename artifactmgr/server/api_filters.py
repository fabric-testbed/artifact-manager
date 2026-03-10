def preprocessing_filter_spec(endpoints):
    # Remove all but DRF API endpoints
    filtered = []
    for (path, path_regex, method, callback) in endpoints:
        # Artifact endpoints
        if path.startswith("/api/artifact"):
            filtered.append((path, path_regex, method, callback))
        # Author endpoints
        if path.startswith("/api/author") and method == 'GET':
            filtered.append((path, path_regex, method, callback))
        # Tag endpoints
        if path.startswith("/api/meta/tags") and method in ['PATCH', 'PUT', 'POST', 'DELETE']:
            filtered.append((path, path_regex, method, callback))
        if path.endswith("/api/meta/tags") and method == 'GET':
            filtered.append((path, path_regex, method, callback))
        # Version endpoints
        if path.endswith("/api/contents"):
            filtered.append((path, path_regex, method, callback))
        if path.startswith("/api/contents") and method in ['PATCH', 'PUT']:
            filtered.append((path, path_regex, method, callback))
        if path.startswith("/api/contents/download") and method == 'GET':
            filtered.append((path, path_regex, method, callback))
    return filtered
