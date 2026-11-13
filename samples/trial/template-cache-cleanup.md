# MyApp template cache cleanup

MyApp keeps compiled templates in `/var/cache/myapp/templates` and never deletes old ones. When the
"inodes above 80%" alert fires on a web server, this is usually why. 10 minutes by hand, about
7 times a month.

- Check inode usage on the filesystem holding /var/cache with `df -i`.
- Count the files in the template cache.
- Delete template cache files (`*.cache`) that haven't been modified for 7 days. Leave the folder
  itself and anything that isn't a `.cache` file.
- Count the files again and check `df -i` once more.
- MyApp rebuilds templates on demand, so no restart is needed. Check the health page on port 8080
  still answers to be sure.
